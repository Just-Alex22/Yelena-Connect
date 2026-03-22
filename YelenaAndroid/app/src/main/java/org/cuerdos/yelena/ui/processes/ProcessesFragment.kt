package org.cuerdos.yelena.ui.processes

import android.app.AlertDialog
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
import org.cuerdos.yelena.databinding.FragmentProcessesBinding
import org.cuerdos.yelena.websocket.YelenaWebSocket

class ProcessesFragment : Fragment() {
    private var _b: FragmentProcessesBinding? = null
    private val b get() = _b!!

    override fun onCreateView(i: LayoutInflater, c: ViewGroup?, s: Bundle?): View {
        _b = FragmentProcessesBinding.inflate(i, c, false); return b.root
    }

    override fun onViewCreated(v: View, s: Bundle?) {
        super.onViewCreated(v, s)
        b.btnBack.setOnClickListener { findNavController().popBackStack() }
        b.btnRefresh.setOnClickListener { YelenaWebSocket.requestProcesses() }

        viewLifecycleOwner.lifecycleScope.launch {
            YelenaWebSocket.processes.collectLatest { list -> updateList(list) }
        }

        // Auto-refresh cada 3s mientras la pantalla está visible
        viewLifecycleOwner.lifecycleScope.launch {
            while (true) {
                YelenaWebSocket.requestProcesses()
                delay(3_000)
            }
        }
    }

    private fun updateList(procs: List<Map<String, Any>>) {
        b.processList.removeAllViews()
        b.tvEmpty.visibility = if (procs.isEmpty()) View.VISIBLE else View.GONE
        if (procs.isEmpty()) return

        val inf = LayoutInflater.from(requireContext())
        procs.forEach { proc ->
            val pid  = proc["pid"]?.toString() ?: "?"
            val name = proc["name"]?.toString() ?: "?"
            val cpu  = proc["cpu"]?.toString()  ?: "0"
            val mem  = proc["mem"]?.toString()  ?: "0"
            val row  = inf.inflate(R.layout.item_process_row, b.processList, false)
            row.findViewById<TextView>(R.id.tvProcName).text  = name
            row.findViewById<TextView>(R.id.tvProcStats).text = "PID $pid  CPU ${cpu}%  MEM ${mem}%"
            row.setOnLongClickListener {
                AlertDialog.Builder(requireContext())
                    .setTitle(getString(R.string.terminate_process))
                    .setMessage(getString(R.string.terminate_confirm, name, pid))
                    .setPositiveButton(getString(R.string.terminate)) { _, _ ->
                        YelenaWebSocket.killProcess(pid.toIntOrNull() ?: 0)
                    }
                    .setNegativeButton(getString(R.string.cancel), null).show()
                true
            }
            b.processList.addView(row)
        }
    }

    override fun onDestroyView() { super.onDestroyView(); _b = null }
}
