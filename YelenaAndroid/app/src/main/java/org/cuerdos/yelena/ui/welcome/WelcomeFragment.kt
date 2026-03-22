package org.cuerdos.yelena.ui.welcome

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.view.*
import androidx.fragment.app.Fragment
import androidx.navigation.fragment.findNavController
import org.cuerdos.yelena.R
import org.cuerdos.yelena.databinding.FragmentWelcomeBinding

class WelcomeFragment : Fragment() {
    private var _b: FragmentWelcomeBinding? = null
    private val b get() = _b!!

    override fun onCreateView(i: LayoutInflater, c: ViewGroup?, s: Bundle?): View {
        _b = FragmentWelcomeBinding.inflate(i, c, false); return b.root
    }

    override fun onViewCreated(v: View, s: Bundle?) {
        super.onViewCreated(v, s)
        b.root.alpha = 0f
        b.root.animate().alpha(1f).setDuration(600).start()
        b.btnComenzar.setOnClickListener {
            findNavController().navigate(R.id.action_welcome_to_connect)
        }
        b.tvPrivacyPolicy.setOnClickListener {
            startActivity(Intent(Intent.ACTION_VIEW,
                Uri.parse("https://cuerdos.github.io/privacidad")))
        }
    }

    override fun onDestroyView() { super.onDestroyView(); _b = null }
}
