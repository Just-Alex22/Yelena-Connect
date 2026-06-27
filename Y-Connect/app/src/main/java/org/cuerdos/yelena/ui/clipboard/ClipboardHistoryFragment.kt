package org.cuerdos.yelena.ui.clipboard

import android.content.ClipboardManager
import android.content.Context
import android.os.Bundle
import android.view.*
import android.view.inputmethod.EditorInfo
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
        _b = FragmentClipboardHistoryBinding.inflate(i, c, false)
        return b.root
    }

    override fun onViewCreated(v: View, s: Bundle?) {
        super.onViewCreated(v, s)

        b.btnBack.setOnClickListener { findNavController().popBackStack() }

        b.btnQuickSend.setOnClickListener { sendQuickText() }
        b.etQuickSend.setOnEditorActionListener { _, actionId, _ ->
            if (actionId == EditorInfo.IME_ACTION_SEND) { sendQuickText(); true } else false
        }

        b.btnPhoneClipToPC.setOnClickListener {
            val cm = requireContext().getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
            val text = cm.primaryClip?.getItemAt(0)
                ?.coerceToText(requireContext())?.toString()
            if (!text.isNullOrEmpty()) {
                YelenaWebSocket.sendClipboard(text)
                Toast.makeText(context, R.string.copied_to_pc, Toast.LENGTH_SHORT).show()
            } else {
                Toast.makeText(context, R.string.no_content, Toast.LENGTH_SHORT).show()
            }
        }

        viewLifecycleOwner.lifecycleScope.launch {
            YelenaWebSocket.clipboardHistory.collectLatest { items -> updateList(items) }
        }
        YelenaWebSocket.requestClipboardHistory()
    }

    private fun sendQuickText() {
        val text = b.etQuickSend.text.toString()
        if (text.isEmpty()) return
        b.etQuickSend.text?.clear()
        YelenaWebSocket.sendClipboard(text)
        YelenaWebSocket.sendKeyPress("ctrl+v")
        Toast.makeText(context, R.string.copied_to_pc, Toast.LENGTH_SHORT).show()
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
                YelenaWebSocket.sendKeyPress("ctrl+v")
                Toast.makeText(context, R.string.copied_to_pc, Toast.LENGTH_SHORT).show()
            }
            b.historyList.addView(row)
        }
    }

    override fun onDestroyView() { super.onDestroyView(); _b = null }
}