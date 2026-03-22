package org.cuerdos.yelena

import android.app.Application

class YelenaApp : Application() {
    companion object {
        lateinit var instance: YelenaApp
            private set
    }
    override fun onCreate() {
        super.onCreate()
        instance = this
    }
}
