package com.uaply.app;

import android.annotation.SuppressLint;
import android.app.AlertDialog;
import android.content.Intent;
import android.graphics.Color;
import android.graphics.Typeface;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.util.Base64;
import android.view.Gravity;
import android.view.ViewGroup;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

import androidx.appcompat.app.AppCompatActivity;
import androidx.core.content.FileProvider;

import org.json.JSONObject;

import java.io.File;
import java.io.FileOutputStream;

/**
 * The employer's own application page, inside the UAply app (docs/assisted-apply.md).
 *
 * Every 1.5 s it asks the page two things: is this the employer's confirmation page (UAplyAssist.confirmed())? and, once per page
 * address, is there a form to fill? It fills that form once from the person's profile (UAplyAssist.fill), attaches their resume, and
 * the page shows "Review and tap Submit". The person reviews it and taps the employer's own Submit button; nothing here presses it.
 * The one exception is mode "automatic", which the app passes only when shared/assist-systems.json allows a hiring system (the owner's
 * lawyer sets it); even then UAplyAssist.submitIfAllowed presses Submit only when the page has no human check of any kind, nothing
 * required is left and the resume is attached. A human check (reCAPTCHA, hCaptcha, Turnstile) is never touched: the person does it.
 *
 * When the person taps the page's own resume box, the phone's file chooser is replaced by a choice: their UAply resume, or another file.
 * The result goes back to AssistPlugin: confirmed is true only when the confirmation page appeared.
 */
public class AssistActivity extends AppCompatActivity {
    private static final int PICK_FILE = 41;
    private WebView web;
    private final Handler tick = new Handler(Looper.getMainLooper());
    private String lastReport = null;
    private boolean finished = false;
    private ValueCallback<Uri[]> pendingChooser = null;
    private WebChromeClient.FileChooserParams pendingParams = null;

    @SuppressLint("SetJavaScriptEnabled")
    @Override
    protected void onCreate(Bundle saved) {
        super.onCreate(saved);
        String url = getIntent().getStringExtra("url");
        String co = getIntent().getStringExtra("co");

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        LinearLayout bar = new LinearLayout(this);
        bar.setOrientation(LinearLayout.HORIZONTAL);
        bar.setGravity(Gravity.CENTER_VERTICAL);
        bar.setBackgroundColor(Color.parseColor("#2A1218"));
        int pad = (int) (12 * getResources().getDisplayMetrics().density);
        bar.setPadding(pad, pad / 2, pad / 2, pad / 2);
        TextView title = new TextView(this);
        title.setText(co == null || co.isEmpty() ? "Applying on the employer's page" : "Applying at " + co);
        title.setTextColor(Color.WHITE);
        title.setTypeface(Typeface.DEFAULT_BOLD);
        title.setTextSize(16);
        bar.addView(title, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        Button close = new Button(this);
        close.setText("Close");
        close.setOnClickListener(v -> done(false, web == null ? "" : web.getUrl()));
        bar.addView(close);
        root.addView(bar, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        web = new WebView(this);
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(true);           // the resume is handed to the page as a content:// address (FileProvider)
        s.setMediaPlaybackRequiresUserGesture(true);
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest req) {
                String u = req.getUrl().toString();
                if (u.startsWith("https://")) return false;   // the employer's pages, its sign-in and its confirmation page
                try { startActivity(new Intent(Intent.ACTION_VIEW, req.getUrl())); } catch (Exception ignored) {}   // mailto:, tel: and the like
                return true;
            }

            @Override
            public void onPageFinished(WebView view, String u) { inject(); }
        });
        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> cb, FileChooserParams params) {
                chooseFile(cb, params);
                return true;
            }
        });
        root.addView(web, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1));
        setContentView(root);
        web.loadUrl(url);
        tick.postDelayed(this::poll, 1500);
    }

    /** puts the assist script into the page once per document (it keeps itself to one copy) */
    private void inject() {
        if (web == null || AssistPlugin.engine.isEmpty()) return;
        web.evaluateJavascript(AssistPlugin.engine, null);
    }

    /** the page's state every 1.5 s: the confirmation page ends it; a form not yet filled at this address gets filled, once */
    private void poll() {
        if (finished || web == null) return;
        String ask = "(function(){if(!window.UAplyAssist)return 'none';var n=document.querySelectorAll('input:not([type=hidden]),textarea,select').length;"
            + "return JSON.stringify({c:UAplyAssist.confirmed(),n:n,ran:window.__uaplyAssistRan===location.href,rep:window.__uaplyRep||null,url:location.href})})()";
        web.evaluateJavascript(ask, v -> {
            try {
                if (v == null || v.equals("null") || v.equals("\"none\"")) { inject(); return; }
                JSONObject o = new JSONObject(new JSONObject("{\"s\":" + v + "}").getString("s"));
                if (!o.isNull("rep")) lastReport = o.optString("rep");
                if (o.optBoolean("c")) {   // the employer's confirmation page: leave it on screen a moment, then report Sent
                    finished = true;
                    final String at = o.optString("url");
                    tick.postDelayed(() -> { finished = false; done(true, at); }, 2500);
                    return;
                }
                if (!o.optBoolean("ran") && o.optInt("n") > 3) fill();
            } catch (Exception ignored) {
            } finally {
                if (!finished) tick.postDelayed(this::poll, 1500);
            }
        });
    }

    /** fills the form once at this address; the profile is a call argument, not a page global, and is dropped after */
    private void fill() {
        String auto = "automatic".equals(AssistPlugin.mode) ? "UAplyAssist.submitIfAllowed('automatic',r);" : "";
        String js = "(function(P,J){window.__uaplyAssistRan=location.href;window.__uaplyRep=null;"
            + "UAplyAssist.fill(P,{job:J,banner:true}).then(function(r){window.__uaplyRep=JSON.stringify({seen:r.seen,filled:r.filled,leftReq:r.leftReq,"
            + "eeoSkipped:r.eeoSkipped,resumeAttached:r.resumeAttached,humanCheck:r.humanCheck,checkKind:r.checkKind,submit:r.submit,ms:r.ms});" + auto + "})"
            + "})(" + AssistPlugin.profileJson + "," + AssistPlugin.jobJson + ")";
        web.evaluateJavascript(js, null);
    }

    /** the page's own resume box: offer the resume the person keeps in UAply first */
    private void chooseFile(ValueCallback<Uri[]> cb, WebChromeClient.FileChooserParams params) {
        if (pendingChooser != null) pendingChooser.onReceiveValue(null);
        pendingChooser = cb;
        pendingParams = params;
        String name = null;
        try { JSONObject r = new JSONObject(AssistPlugin.profileJson).optJSONObject("resume"); if (r != null) name = r.optString("name", null); } catch (Exception ignored) {}
        AlertDialog.Builder b = new AlertDialog.Builder(this).setTitle("Attach a file");
        if (name != null) b.setMessage("Your UAply resume: " + name).setPositiveButton("Use my UAply resume", (d, w) -> giveResume());
        b.setNeutralButton("Choose another file", (d, w) -> pickOther());
        b.setNegativeButton("Cancel", (d, w) -> answerChooser(null));
        b.setOnCancelListener(d -> answerChooser(null));
        b.show();
    }

    private void giveResume() {
        try {
            JSONObject r = new JSONObject(AssistPlugin.profileJson).getJSONObject("resume");
            String safe = r.optString("name", "resume.pdf").replaceAll("[^A-Za-z0-9._ -]", "_");
            File dir = new File(getCacheDir(), "assist");
            if (!dir.exists() && !dir.mkdirs()) throw new Exception("no cache folder");
            File f = new File(dir, safe);
            try (FileOutputStream out = new FileOutputStream(f)) { out.write(Base64.decode(r.getString("b64"), Base64.DEFAULT)); }
            Uri uri = FileProvider.getUriForFile(this, getPackageName() + ".fileprovider", f);
            answerChooser(new Uri[]{uri});
        } catch (Exception e) {
            pickOther();
        }
    }

    private void pickOther() {
        try {
            Intent i = pendingParams != null ? pendingParams.createIntent() : new Intent(Intent.ACTION_GET_CONTENT).setType("*/*");
            startActivityForResult(i, PICK_FILE);
        } catch (Exception e) { answerChooser(null); }
    }

    private void answerChooser(Uri[] uris) {
        if (pendingChooser != null) pendingChooser.onReceiveValue(uris);
        pendingChooser = null;
        pendingParams = null;
    }

    @Override
    protected void onActivityResult(int req, int res, Intent data) {
        super.onActivityResult(req, res, data);
        if (req == PICK_FILE) answerChooser(WebChromeClient.FileChooserParams.parseResult(res, data));
    }

    @Override
    public void onBackPressed() {
        if (web != null && web.canGoBack()) web.goBack();
        else done(false, web == null ? "" : web.getUrl());
    }

    private void done(boolean confirmed, String url) {
        if (finished) return;
        finished = true;
        tick.removeCallbacksAndMessages(null);
        Intent r = new Intent();
        r.putExtra("confirmed", confirmed);
        r.putExtra("url", url == null ? "" : url);
        r.putExtra("report", lastReport);
        setResult(RESULT_OK, r);
        File dir = new File(getCacheDir(), "assist");      // the resume copy handed to the page does not stay on the phone
        File[] fs = dir.listFiles();
        if (fs != null) for (File f : fs) //noinspection ResultOfMethodCallIgnored
            f.delete();
        if (web != null) { web.stopLoading(); web.destroy(); web = null; }
        finish();
    }
}
