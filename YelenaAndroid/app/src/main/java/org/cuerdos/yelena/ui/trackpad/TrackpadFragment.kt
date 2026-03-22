package org.cuerdos.yelena.ui.trackpad

import android.os.Bundle
import android.view.*
import android.view.inputmethod.EditorInfo
import androidx.fragment.app.Fragment
import androidx.navigation.fragment.findNavController
import org.cuerdos.yelena.databinding.FragmentTrackpadBinding
import org.cuerdos.yelena.websocket.YelenaWebSocket

class TrackpadFragment : Fragment() {
    private var _b: FragmentTrackpadBinding? = null
    private val b get() = _b!!

    override fun onCreateView(i: LayoutInflater, c: ViewGroup?, s: Bundle?): View {
        _b = FragmentTrackpadBinding.inflate(i, c, false)
        return b.root
    }

    override fun onViewCreated(v: View, s: Bundle?) {
        super.onViewCreated(v, s)
        b.root.alpha = 0f; b.root.animate().alpha(1f).setDuration(300).start()
        b.btnBack.setOnClickListener { findNavController().popBackStack() }

        // Enviar texto al PC
        b.btnSend.setOnClickListener { sendText() }
        b.etInput.setOnEditorActionListener { _, actionId, _ ->
            if (actionId == EditorInfo.IME_ACTION_SEND) { sendText(); true } else false
        }

        // Teclas especiales
        b.btnEsc.setOnClickListener       { YelenaWebSocket.sendKeyPress("Escape") }
        b.btnTab.setOnClickListener       { YelenaWebSocket.sendKeyPress("Tab") }
        b.btnEnter.setOnClickListener     { YelenaWebSocket.sendKeyPress("Return") }
        b.btnBackspace.setOnClickListener { YelenaWebSocket.sendKeyPress("BackSpace") }
        b.btnUp.setOnClickListener        { YelenaWebSocket.sendKeyPress("Up") }
        b.btnDown.setOnClickListener      { YelenaWebSocket.sendKeyPress("Down") }
        b.btnLeft.setOnClickListener      { YelenaWebSocket.sendKeyPress("Left") }
        b.btnRight.setOnClickListener     { YelenaWebSocket.sendKeyPress("Right") }
        b.btnCtrlC.setOnClickListener     { YelenaWebSocket.sendKeyPress("ctrl+c") }
        b.btnCtrlV.setOnClickListener     { YelenaWebSocket.sendKeyPress("ctrl+v") }
        b.btnCtrlZ.setOnClickListener     { YelenaWebSocket.sendKeyPress("ctrl+z") }
        b.btnCtrlA.setOnClickListener     { YelenaWebSocket.sendKeyPress("ctrl+a") }
    }

    private fun sendText() {
        val text = b.etInput.text.toString()
        if (text.isNotEmpty()) {
            YelenaWebSocket.sendTypeText(text)
            b.etInput.text?.clear()
        }
    }

    override fun onDestroyView() { super.onDestroyView(); _b = null }
}
