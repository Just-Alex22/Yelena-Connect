package org.cuerdos.yelena.ui.terminal

import android.os.Bundle
import android.view.*
import android.view.inputmethod.EditorInfo
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import androidx.navigation.fragment.findNavController
import kotlinx.coroutines.launch
import org.cuerdos.yelena.databinding.FragmentTerminalBinding
import org.cuerdos.yelena.websocket.YelenaWebSocket

class TerminalFragment : Fragment() {
    private var _b: FragmentTerminalBinding? = null
    private val b get() = _b!!
    private val history = StringBuilder()

    override fun onCreateView(i: LayoutInflater, c: ViewGroup?, s: Bundle?): View {
        _b = FragmentTerminalBinding.inflate(i, c, false); return b.root
    }

    override fun onViewCreated(v: View, s: Bundle?) {
        super.onViewCreated(v, s)
        b.root.alpha = 0f; b.root.animate().alpha(1f).setDuration(300).start()
        b.btnBack.setOnClickListener { findNavController().popBackStack() }

        // SharedFlow con collect (no collectLatest) — emite cada output siempre
        viewLifecycleOwner.lifecycleScope.launch {
            YelenaWebSocket.terminalOutput.collect { output ->
                history.append("${output.output}\n")
                b.tvOutput.text = history
                b.scrollOutput.post { b.scrollOutput.fullScroll(View.FOCUS_DOWN) }
            }
        }

        b.etCommand.setOnEditorActionListener { _, actionId, _ ->
            if (actionId == EditorInfo.IME_ACTION_SEND) { sendCmd(); true } else false
        }
        b.btnSend.setOnClickListener { sendCmd() }
    }

    private fun sendCmd() {
        val cmd = b.etCommand.text.toString().trim()
        if (cmd.isNotEmpty()) {
            history.append("$ $cmd\n")
            b.tvOutput.text = history
            b.etCommand.text?.clear()
            YelenaWebSocket.sendTerminalCommand(cmd)
        }
    }

    override fun onDestroyView() { super.onDestroyView(); _b = null }
}
