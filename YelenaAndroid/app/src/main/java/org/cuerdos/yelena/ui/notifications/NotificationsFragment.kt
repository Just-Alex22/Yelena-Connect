package org.cuerdos.yelena.ui.notifications

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
import org.cuerdos.yelena.databinding.FragmentNotificationsBinding
import org.cuerdos.yelena.model.PcNotification
import org.cuerdos.yelena.websocket.YelenaWebSocket

class NotificationsFragment : Fragment() {
    private var _b: FragmentNotificationsBinding? = null
    private val b get() = _b!!

    override fun onCreateView(i: LayoutInflater, c: ViewGroup?, s: Bundle?): View {
        _b = FragmentNotificationsBinding.inflate(i, c, false); return b.root
    }

    override fun onViewCreated(v: View, s: Bundle?) {
        super.onViewCreated(v, s)
        b.root.alpha = 0f; b.root.animate().alpha(1f).setDuration(300).start()
        b.btnBack.setOnClickListener { findNavController().popBackStack() }

        viewLifecycleOwner.lifecycleScope.launch {
            YelenaWebSocket.pcNotifications.collectLatest { updateList(it) }
        }
    }

    private fun updateList(notifs: List<PcNotification>) {
        b.notifContainer.removeAllViews()
        b.tvEmpty.visibility = if (notifs.isEmpty()) View.VISIBLE else View.GONE
        if (notifs.isEmpty()) return
        val inf = LayoutInflater.from(requireContext())
        notifs.forEach { n ->
            val item = inf.inflate(R.layout.item_notification, b.notifContainer, false)
            item.findViewById<TextView>(R.id.tvNotifApp).text   = n.app
            item.findViewById<TextView>(R.id.tvNotifTitle).text = n.title
            item.findViewById<TextView>(R.id.tvNotifBody).text  = n.body
            b.notifContainer.addView(item)
        }
    }

    override fun onDestroyView() { super.onDestroyView(); _b = null }
}
