package com.uaply.app;

import android.os.Bundle;

import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(AssistPlugin.class);   // assisted apply on employers' own pages (docs/assisted-apply.md)
        super.onCreate(savedInstanceState);
    }
}
