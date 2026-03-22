package org.cuerdos.yelena.ui.apps

import android.os.Bundle
import android.view.*
import android.widget.TextView
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import androidx.navigation.fragment.findNavController
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch
import org.cuerdos.yelena.R
import org.cuerdos.yelena.databinding.FragmentAppsBinding
import org.cuerdos.yelena.websocket.YelenaWebSocket

class AppsFragment : Fragment() {
    private var _b: FragmentAppsBinding? = null
    private val b get() = _b!!

    override fun onCreateView(i: LayoutInflater, c: ViewGroup?, s: Bundle?): View {
        _b = FragmentAppsBinding.inflate(i, c, false); return b.root
    }

    override fun onViewCreated(v: View, s: Bundle?) {
        super.onViewCreated(v, s)
        b.btnBack.setOnClickListener { findNavController().popBackStack() }

        viewLifecycleOwner.lifecycleScope.launch {
            YelenaWebSocket.apps.collectLatest { list -> updateList(list) }
        }

        viewLifecycleOwner.lifecycleScope.launch {
            while (true) {
                YelenaWebSocket.requestApps()
                delay(5_000)
            }
        }
    }

    private fun updateList(apps: List<Map<String, String>>) {
        b.appList.removeAllViews()
        b.tvEmpty.visibility = if (apps.isEmpty()) View.VISIBLE else View.GONE
        if (apps.isEmpty()) return
        val inf = LayoutInflater.from(requireContext())
        apps.forEach { app ->
            val row = inf.inflate(R.layout.item_app_row, b.appList, false)
            row.findViewById<TextView>(R.id.tvAppName).text = app["name"] ?: "?"
            row.setOnClickListener { YelenaWebSocket.launchApp(app["exec"] ?: return@setOnClickListener) }
            b.appList.addView(row)
        }
    }

    override fun onDestroyView() { super.onDestroyView(); _b = null }
}
