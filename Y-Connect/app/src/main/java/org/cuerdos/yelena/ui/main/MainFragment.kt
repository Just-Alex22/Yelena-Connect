package org.cuerdos.yelena.ui.main

import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.res.ColorStateList
import android.graphics.Bitmap
import android.media.MediaMetadata
import android.media.session.MediaSessionManager
import android.media.session.PlaybackState
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.BatteryManager
import android.os.Build
import android.os.Bundle
import android.util.Base64
import android.util.TypedValue
import android.view.*
import androidx.core.view.GravityCompat
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import androidx.navigation.fragment.findNavController
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch
import org.cuerdos.yelena.R
import org.cuerdos.yelena.databinding.FragmentMainBinding
import org.cuerdos.yelena.model.*
import org.cuerdos.yelena.websocket.ConnectionState
import org.cuerdos.yelena.websocket.YelenaWebSocket
import java.io.ByteArrayOutputStream

class MainFragment : Fragment() {
    private var _binding: FragmentMainBinding? = null
    private val binding get() = _binding!!

    private var lastMediaTitle   = ""
    private var lastMediaArtist  = ""
    private var lastMediaPlaying = false
    private var lastArtworkHash  = 0

    override fun onCreateView(i: LayoutInflater, c: ViewGroup?, s: Bundle?): View {
        _binding = FragmentMainBinding.inflate(i, c, false)
        return binding.root
    }

    override fun onViewCreated(view: View, s: Bundle?) {
        super.onViewCreated(view, s)
        binding.root.alpha = 0f
        binding.root.animate().alpha(1f).setDuration(400).start()
        applyAccentTints()
        setupDrawer()
        setupMediaControls()
        binding.cardTerminal.setOnClickListener {
            findNavController().navigate(R.id.action_main_to_terminal)
        }
        binding.cardTrackpad.setOnClickListener {
            findNavController().navigate(R.id.action_main_to_trackpad)
        }
        observeState()
    }

    private fun resolveAccentColor(): Int {
        val tv = TypedValue()
        val resolved = requireContext().theme.resolveAttribute(
            com.google.android.material.R.attr.colorPrimary, tv, true)
        if (resolved && tv.type >= TypedValue.TYPE_FIRST_COLOR_INT
                     && tv.type <= TypedValue.TYPE_LAST_COLOR_INT) return tv.data
        requireContext().theme.resolveAttribute(android.R.attr.colorPrimary, tv, true)
        return tv.data
    }

    private fun applyAccentTints() {
        val tint = ColorStateList.valueOf(resolveAccentColor())
        binding.rowCpu.progressRes.progressTintList  = tint
        binding.rowRam.progressRes.progressTintList  = tint
        binding.rowDisk.progressRes.progressTintList = tint
    }

    private fun setupDrawer() {
        binding.btnMenu.setOnClickListener {
            binding.drawerLayout.openDrawer(GravityCompat.START)
        }
        binding.navView.setNavigationItemSelectedListener { item ->
            binding.drawerLayout.closeDrawers()
            when (item.itemId) {
                R.id.nav_terminal      -> { findNavController().navigate(R.id.action_main_to_terminal);      true }
                R.id.nav_notifications -> { findNavController().navigate(R.id.action_main_to_notifications); true }
                R.id.nav_processes     -> { findNavController().navigate(R.id.action_main_to_processes);     true }
                R.id.nav_trackpad      -> { findNavController().navigate(R.id.action_main_to_trackpad);      true }
                R.id.nav_apps          -> { findNavController().navigate(R.id.action_main_to_apps);          true }
                R.id.nav_clipboard     -> { findNavController().navigate(R.id.action_main_to_clipboard);     true }
                R.id.nav_settings      -> { findNavController().navigate(R.id.action_main_to_settings);      true }
                R.id.nav_about         -> { findNavController().navigate(R.id.action_main_to_about);         true }
                R.id.nav_disconnect    -> {
                    requireContext()
                        .getSharedPreferences("yelena_prefs", Context.MODE_PRIVATE)
                        .edit().remove("last_ip").remove("last_port").apply()
                    YelenaWebSocket.disconnect()
                    findNavController().navigate(R.id.action_main_to_connect)
                    true
                }
                else -> false
            }
        }
    }

    private fun setupMediaControls() {
        binding.btnPrev.setOnClickListener      { YelenaWebSocket.sendMediaCommand("prev") }
        binding.btnPlayPause.setOnClickListener { YelenaWebSocket.sendMediaCommand("play_pause") }
        binding.btnNext.setOnClickListener      { YelenaWebSocket.sendMediaCommand("next") }
        binding.btnVolDown.setOnClickListener   { YelenaWebSocket.sendMediaCommand("vol_down") }
        binding.btnVolUp.setOnClickListener     { YelenaWebSocket.sendMediaCommand("vol_up") }
    }

    private fun observeState() {
        viewLifecycleOwner.lifecycleScope.launch {
            YelenaWebSocket.connectionState.collectLatest { state ->
                when (state) {
                    is ConnectionState.Connected -> {
                        binding.tvConnectionStatus.text =
                            getString(R.string.connected_to, state.pcInfo.hostname)
                        binding.tvConnectionStatus.setTextColor(resolveAccentColor())
                        binding.connectionDot.backgroundTintList =
                            ColorStateList.valueOf(resolveAccentColor())
                        sendAccentColor()
                        YelenaWebSocket.lastBatteryPct    = -1
                        YelenaWebSocket.lastBatteryCharge = false
                        YelenaWebSocket.lastRssi          = Int.MIN_VALUE
                    }
                    is ConnectionState.Connecting -> {
                        binding.tvConnectionStatus.setText(R.string.connecting)
                        binding.tvConnectionStatus.setTextColor(
                            requireContext().getColor(R.color.text_secondary))
                        binding.connectionDot.backgroundTintList = null
                        binding.connectionDot.setBackgroundResource(R.drawable.shape_dot)
                    }
                    is ConnectionState.Disconnected -> {
                        binding.tvConnectionStatus.setText(R.string.disconnected)
                        binding.tvConnectionStatus.setTextColor(
                            requireContext().getColor(R.color.text_disabled))
                        binding.connectionDot.backgroundTintList = null
                        binding.connectionDot.setBackgroundResource(R.drawable.shape_dot)
                    }
                    is ConnectionState.Error -> {
                        binding.tvConnectionStatus.text =
                            getString(R.string.error_prefix, state.message)
                        binding.tvConnectionStatus.setTextColor(
                            requireContext().getColor(R.color.accent_red))
                        binding.connectionDot.backgroundTintList = null
                        binding.connectionDot.setBackgroundResource(R.drawable.shape_dot)
                    }
                }
            }
        }
        viewLifecycleOwner.lifecycleScope.launch {
            YelenaWebSocket.pcResources.collectLatest { updateResources(it) }
        }
        viewLifecycleOwner.lifecycleScope.launch {
            YelenaWebSocket.pcMedia.collectLatest { updateMedia(it) }
        }
        viewLifecycleOwner.lifecycleScope.launch {
            while (true) {
                sendWifiSignal()
                sendBattery()
                sendPhoneMedia()
                delay(5_000)
            }
        }
    }

    private fun sendAccentColor() {
        val prefs = requireContext().getSharedPreferences("yelena_prefs", Context.MODE_PRIVATE)
        val hex = prefs.getString("accent_color", "#5a7a22") ?: "#5a7a22"
        YelenaWebSocket.sendAccentColor(hex)
    }

    private fun sendPhoneMedia() {
        try {
            val msm = requireContext().getSystemService(Context.MEDIA_SESSION_SERVICE) as MediaSessionManager
            val cn = android.content.ComponentName(requireContext(), org.cuerdos.yelena.YelenaNotificationListener::class.java)
            val ctrl = msm.getActiveSessions(cn).firstOrNull() ?: return
            val meta    = ctrl.metadata
            val state   = ctrl.playbackState
            val title   = meta?.getString(MediaMetadata.METADATA_KEY_TITLE)  ?: ""
            val artist  = meta?.getString(MediaMetadata.METADATA_KEY_ARTIST) ?: ""
            val playing = state?.state == PlaybackState.STATE_PLAYING
            val rawBitmap = meta?.getBitmap(MediaMetadata.METADATA_KEY_ALBUM_ART)
                ?: meta?.getBitmap(MediaMetadata.METADATA_KEY_ART)
            val bitmapHash = rawBitmap?.hashCode() ?: 0
            val changed = title   != lastMediaTitle
                       || artist  != lastMediaArtist
                       || playing != lastMediaPlaying
                       || bitmapHash != lastArtworkHash
            if (!changed) return
            lastMediaTitle   = title
            lastMediaArtist  = artist
            lastMediaPlaying = playing
            lastArtworkHash  = bitmapHash
            val artwork = rawBitmap?.let { bmp ->
                val scaled = Bitmap.createScaledBitmap(bmp, 200, 200, true)
                val out = ByteArrayOutputStream()
                scaled.compress(Bitmap.CompressFormat.JPEG, 75, out)
                Base64.encodeToString(out.toByteArray(), Base64.NO_WRAP)
            }
            YelenaWebSocket.sendPhoneMedia(title, artist, playing, artwork)
        } catch (_: Exception) {}
    }

    private fun sendBattery() {
        try {
            val intent = requireContext().registerReceiver(
                null, IntentFilter(Intent.ACTION_BATTERY_CHANGED)) ?: return
            val level   = intent.getIntExtra(BatteryManager.EXTRA_LEVEL, -1)
            val scale   = intent.getIntExtra(BatteryManager.EXTRA_SCALE, -1)
            if (level < 0 || scale <= 0) return
            val pct      = level * 100 / scale
            val status   = intent.getIntExtra(BatteryManager.EXTRA_STATUS, -1)
            val charging = status == BatteryManager.BATTERY_STATUS_CHARGING
                        || status == BatteryManager.BATTERY_STATUS_FULL
            if (pct == YelenaWebSocket.lastBatteryPct && charging == YelenaWebSocket.lastBatteryCharge) return
            YelenaWebSocket.sendBattery(pct, charging)
        } catch (_: Exception) {}
    }

    private fun sendWifiSignal() {
        try {
            val cm = requireContext().applicationContext
                .getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
            val rssi: Int
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                val caps = cm.getNetworkCapabilities(cm.activeNetwork ?: return) ?: return
                if (!caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI)) return
                val s = caps.signalStrength
                if (s == NetworkCapabilities.SIGNAL_STRENGTH_UNSPECIFIED) return
                rssi = s
            } else {
                @Suppress("DEPRECATION")
                val wm = requireContext().applicationContext
                    .getSystemService(Context.WIFI_SERVICE) as android.net.wifi.WifiManager
                @Suppress("DEPRECATION")
                rssi = wm.connectionInfo?.rssi ?: return
            }
            if (rssi > -120 && rssi != YelenaWebSocket.lastRssi) {
                YelenaWebSocket.sendWifiSignal(rssi)
            }
        } catch (_: Exception) {}
    }

    private fun updateResources(res: PcResources) {
        binding.rowCpu.tvResLabel.text       = getString(R.string.cpu_label)
        binding.rowCpu.tvResValue.text       = "${res.cpuPercent.toInt()}%"
        binding.rowCpu.progressRes.progress  = res.cpuPercent.toInt()
        binding.rowRam.tvResLabel.text       = getString(R.string.ram_label)
        binding.rowRam.tvResValue.text       = "${"%.1f".format(res.ramUsedGb)}/${"%.1f".format(res.ramTotalGb)} GB"
        binding.rowRam.progressRes.progress  = res.ramPercent.toInt()
        binding.rowDisk.tvResLabel.text      = getString(R.string.disk_label)
        binding.rowDisk.tvResValue.text      = "${"%.1f".format(res.diskUsedGb)}/${"%.1f".format(res.diskTotalGb)} GB"
        binding.rowDisk.progressRes.progress = res.diskPercent.toInt()
        val h = res.uptimeSeconds / 3600
        val m = (res.uptimeSeconds % 3600) / 60
        binding.tvUptime.text = "${h}h ${m}m"
    }

    private fun updateMedia(media: PcMedia) {
        binding.tvMediaTitle.visibility  = if (media.title.isNotBlank())  View.VISIBLE else View.GONE
        binding.tvMediaArtist.visibility = if (media.artist.isNotBlank()) View.VISIBLE else View.GONE
        binding.tvMediaTitle.text  = media.title
        binding.tvMediaArtist.text = media.artist
        binding.btnPlayPause.setImageResource(
            if (media.playing) R.drawable.ic_pause else R.drawable.ic_play)
    }

    override fun onDestroyView() { super.onDestroyView(); _binding = null }
}