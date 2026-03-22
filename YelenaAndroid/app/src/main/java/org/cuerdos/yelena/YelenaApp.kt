package org.cuerdos.yelena
import android.app.Application
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.preferencesDataStore
val Application.dataStore: DataStore<Preferences> by preferencesDataStore(name = "yelena_prefs")
class YelenaApp : Application() {
    companion object { lateinit var instance: YelenaApp private set }
    override fun onCreate() { super.onCreate(); instance = this }
}
