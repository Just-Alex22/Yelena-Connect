package org.cuerdos.yelena.ui.about

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import androidx.fragment.app.Fragment
import androidx.navigation.fragment.findNavController
import org.cuerdos.yelena.databinding.FragmentAboutBinding

class AboutFragment : Fragment() {
    private var _b: FragmentAboutBinding? = null
    private val b get() = _b!!

    override fun onCreateView(i: LayoutInflater, c: ViewGroup?, s: Bundle?): View {
        _b = FragmentAboutBinding.inflate(i, c, false)
        return b.root
    }

    override fun onViewCreated(v: View, s: Bundle?) {
        super.onViewCreated(v, s)
        b.btnBack.setOnClickListener { findNavController().popBackStack() }
        b.cardGithub.setOnClickListener {
            startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("https://cuerdos.github.io")))
        }
    }

    override fun onDestroyView() { super.onDestroyView(); _b = null }
}
