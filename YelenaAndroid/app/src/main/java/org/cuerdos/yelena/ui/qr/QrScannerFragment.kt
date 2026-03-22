package org.cuerdos.yelena.ui.qr

import android.content.Context
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Toast
import androidx.fragment.app.Fragment
import androidx.navigation.fragment.findNavController
import com.journeyapps.barcodescanner.BarcodeCallback
import com.journeyapps.barcodescanner.BarcodeResult
import com.journeyapps.barcodescanner.DefaultDecoderFactory
import com.google.zxing.BarcodeFormat
import kotlinx.serialization.json.Json
import org.cuerdos.yelena.R
import org.cuerdos.yelena.databinding.FragmentQrScannerBinding
import org.cuerdos.yelena.model.QrPayload
import org.cuerdos.yelena.network.YelenaDiscovery
import org.cuerdos.yelena.websocket.YelenaWebSocket

class QrScannerFragment : Fragment() {

    private var _b: FragmentQrScannerBinding? = null
    private val b get() = _b!!
    private val json = Json { ignoreUnknownKeys = true }
    private var scanning = false

    override fun onCreateView(i: LayoutInflater, c: ViewGroup?, s: Bundle?): View {
        _b = FragmentQrScannerBinding.inflate(i, c, false)
        return b.root
    }

    override fun onViewCreated(v: View, s: Bundle?) {
        super.onViewCreated(v, s)
        activity?.requestedOrientation =
            android.content.pm.ActivityInfo.SCREEN_ORIENTATION_PORTRAIT

        b.barcodeView.decoderFactory = DefaultDecoderFactory(listOf(BarcodeFormat.QR_CODE))
        b.barcodeView.cameraSettings.isAutoFocusEnabled = true
        b.barcodeView.decodeContinuous(object : BarcodeCallback {
            override fun barcodeResult(result: BarcodeResult) {
                if (!scanning) return
                scanning = false
                b.barcodeView.pause()
                handleResult(result.text)
            }
        })
        b.btnBack.setOnClickListener {
            activity?.requestedOrientation =
                android.content.pm.ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED
            findNavController().popBackStack()
        }
    }

    override fun onResume()  { super.onResume();  scanning = true;  b.barcodeView.resume() }
    override fun onPause()   { super.onPause();   scanning = false; b.barcodeView.pause() }

    private fun handleResult(raw: String) {
        try {
            val p = json.decodeFromString<QrPayload>(raw)
            // Guardar para reconexión automática
            requireContext()
                .getSharedPreferences("yelena_prefs", Context.MODE_PRIVATE)
                .edit()
                .putString("last_ip", p.ip)
                .putInt("last_port", p.port)
                .apply()

            YelenaDiscovery.stop()
            YelenaWebSocket.connect(p.ip, p.port)
            activity?.requestedOrientation =
                android.content.pm.ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED
            findNavController().navigate(R.id.action_qrScanner_to_main)
        } catch (e: Exception) {
            Toast.makeText(context, "QR inválido", Toast.LENGTH_SHORT).show()
            scanning = true
            b.barcodeView.resume()
        }
    }

    override fun onDestroyView() {
        super.onDestroyView()
        activity?.requestedOrientation =
            android.content.pm.ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED
        _b = null
    }
}
