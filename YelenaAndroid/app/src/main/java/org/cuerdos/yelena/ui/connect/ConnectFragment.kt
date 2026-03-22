package org.cuerdos.yelena.ui.connect

import android.content.Context
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import android.widget.Toast
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import androidx.navigation.fragment.findNavController
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch
import org.cuerdos.yelena.R
import org.cuerdos.yelena.databinding.FragmentConnectBinding
import org.cuerdos.yelena.network.DiscoveredDevice
import org.cuerdos.yelena.network.YelenaDiscovery
import org.cuerdos.yelena.websocket.YelenaWebSocket

class ConnectFragment : Fragment() {
    private var _b: FragmentConnectBinding? = null
    private val b get() = _b!!

    override fun onCreateView(i: LayoutInflater, c: ViewGroup?, s: Bundle?): View {
        _b = FragmentConnectBinding.inflate(i, c, false)
        return b.root
    }

    override fun onViewCreated(v: View, s: Bundle?) {
        super.onViewCreated(v, s)
        b.root.alpha = 0f
        b.root.animate().alpha(1f).setDuration(300).start()
        b.toolbar.setNavigationOnClickListener { findNavController().popBackStack() }

        YelenaDiscovery.start()

        viewLifecycleOwner.lifecycleScope.launch {
            YelenaDiscovery.devices.collectLatest { updateDiscoveredList(it) }
        }

        b.btnScanQr.setOnClickListener {
            findNavController().navigate(R.id.action_connect_to_qrScanner)
        }

        b.btnConnect.setOnClickListener {
            val ip   = b.etIp.text.toString().trim()
            val port = b.etPort.text.toString().trim().toIntOrNull() ?: 8765
            if (ip.isNotEmpty()) connectTo(ip, port, ip)
            else Toast.makeText(context, "Ingresa una IP", Toast.LENGTH_SHORT).show()
        }
    }

    private fun updateDiscoveredList(devices: List<DiscoveredDevice>) {
        b.discoveredList.removeAllViews()
        if (devices.isEmpty()) {
            b.tvDiscoveryStatus.visibility = View.VISIBLE
            b.progressDiscovery.visibility = View.VISIBLE
            return
        }
        b.tvDiscoveryStatus.visibility = View.GONE
        b.progressDiscovery.visibility = View.GONE
        devices.forEach { device ->
            val row = LayoutInflater.from(requireContext())
                .inflate(R.layout.item_device_row, b.discoveredList, false)
            row.findViewById<TextView>(R.id.tvDeviceName).text = device.name
            row.findViewById<TextView>(R.id.tvDeviceSub).text  =
                "${device.os}  ·  ${device.ip}:${device.port}"
            row.setOnClickListener { connectTo(device.ip, device.port, device.name) }
            b.discoveredList.addView(row)
        }
    }

    private fun connectTo(ip: String, port: Int, name: String) {
        // Guardar para reconexión automática
        requireContext()
            .getSharedPreferences("yelena_prefs", Context.MODE_PRIVATE)
            .edit()
            .putString("last_ip", ip)
            .putInt("last_port", port)
            .apply()

        YelenaDiscovery.stop()
        YelenaWebSocket.connect(ip, port)
        findNavController().navigate(R.id.action_connect_to_main)
    }

    override fun onDestroyView() {
        super.onDestroyView()
        YelenaDiscovery.stop()
        _b = null
    }
}
