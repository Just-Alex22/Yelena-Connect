package org.cuerdos.yelena.ui.clipboard

import android.os.Bundle
import android.view.*
import android.widget.TextView
import android.widget.Toast
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import androidx.navigation.fragment.findNavController
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch
import org.cuerdos.yelena.R
import org.cuerdos.yelena.databinding.FragmentClipboardHistoryBinding
import org.cuerdos.yelena.websocket.YelenaWebSocket

class ClipboardHistoryFragment : Fragment() {
    private var _b: FragmentClipboardHistoryBinding? = null
    private val b get() = _b!!

    override fun onCreateView(i: LayoutInflater, c: ViewGroup?, s: Bundle?): View {
        _b = FragmentClipboardHistoryBinding.inflate(i, c, false); return b.root
    }

    override fun onViewCreated(v: View, s: Bundle?) {
        super.onViewCreated(v, s)
        b.btnBack.setOnClickListener { findNavController().popBackStack() }
        viewLifecycleOwner.lifecycleScope.launch {
            YelenaWebSocket.clipboardHistory.collectLatest { items -> updateList(items) }
        }
        YelenaWebSocket.requestClipboardHistory()
    }

    private fun updateList(items: List<String>) {
        b.historyList.removeAllViews()
        b.tvEmpty.visibility = if (items.isEmpty()) View.VISIBLE else View.GONE
        if (items.isEmpty()) return
        val inf = LayoutInflater.from(requireContext())
        items.forEach { text ->
            val row = inf.inflate(R.layout.item_clipboard_row, b.historyList, false)
            row.findViewById<TextView>(R.id.tvClipText).text = text
            row.setOnClickListener {
                YelenaWebSocket.sendClipboard(text)
                Toast.makeText(context, "Copiado al PC", Toast.LENGTH_SHORT).show()
            }
            b.historyList.addView(row)
        }
    }

    override fun onDestroyView() { super.onDestroyView(); _b = null }
}
