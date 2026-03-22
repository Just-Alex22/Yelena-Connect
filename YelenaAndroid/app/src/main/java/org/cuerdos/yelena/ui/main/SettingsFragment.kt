package org.cuerdos.yelena.ui.main

import android.content.Context
import android.os.Bundle
import android.view.*
import androidx.appcompat.app.AppCompatDelegate
import androidx.core.os.LocaleListCompat
import androidx.fragment.app.Fragment
import androidx.navigation.fragment.findNavController
import org.cuerdos.yelena.databinding.FragmentSettingsBinding

class SettingsFragment : Fragment() {
    private var _b: FragmentSettingsBinding? = null
    private val b get() = _b!!

    override fun onCreateView(i: LayoutInflater, c: ViewGroup?, s: Bundle?): View {
        _b = FragmentSettingsBinding.inflate(i, c, false); return b.root
    }

    override fun onViewCreated(v: View, s: Bundle?) {
        super.onViewCreated(v, s)
        b.root.alpha = 0f; b.root.animate().alpha(1f).setDuration(300).start()
        b.btnBack.setOnClickListener { findNavController().popBackStack() }

        val prefs = requireContext().getSharedPreferences("yelena_prefs", Context.MODE_PRIVATE)

        // ── Tema ──────────────────────────────────────────────────────────────
        b.switchTheme.isChecked =
            prefs.getInt("theme_mode", AppCompatDelegate.MODE_NIGHT_FOLLOW_SYSTEM) !=
            AppCompatDelegate.MODE_NIGHT_NO
        b.switchTheme.setOnCheckedChangeListener { _, checked ->
            val mode = if (checked) AppCompatDelegate.MODE_NIGHT_FOLLOW_SYSTEM
                       else AppCompatDelegate.MODE_NIGHT_NO
            AppCompatDelegate.setDefaultNightMode(mode)
            prefs.edit().putInt("theme_mode", mode).apply()
        }

        // ── Idioma ────────────────────────────────────────────────────────────
        // Leer el idioma actualmente activo en la app
        val activeLang = AppCompatDelegate.getApplicationLocales()
            .toLanguageTags()
            .split(",")
            .firstOrNull()
            ?.take(2)
            ?.ifEmpty { null }
            // Si no hay locale de app, usar el del sistema
            ?: resources.configuration.locales[0].language

        // Marcar el radio correcto sin disparar el listener
        b.rgLanguage.setOnCheckedChangeListener(null)
        when (activeLang) {
            "es" -> b.rbEs.isChecked = true
            "en" -> b.rbEn.isChecked = true
            "pt" -> b.rbPt.isChecked = true
            "ca" -> b.rbCa.isChecked = true
            else -> b.rbEs.isChecked = true
        }

        b.rgLanguage.setOnCheckedChangeListener { _, id ->
            val lang = when (id) {
                b.rbEs.id -> "es"
                b.rbEn.id -> "en"
                b.rbPt.id -> "pt"
                b.rbCa.id -> "ca"
                else      -> return@setOnCheckedChangeListener
            }
            // No hacer nada si ya es el idioma activo
            if (lang == activeLang) return@setOnCheckedChangeListener

            // Aplicar idioma — Android recrea la Activity automáticamente
            // porque el Manifest tiene configChanges="locale|layoutDirection"
            AppCompatDelegate.setApplicationLocales(
                LocaleListCompat.forLanguageTags(lang)
            )
        }
    }

    override fun onDestroyView() { super.onDestroyView(); _b = null }
}
