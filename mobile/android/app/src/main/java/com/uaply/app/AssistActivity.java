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
 *
 * What the page can get (October 22 review): nothing at all on a host that is not allowed (AssistPlugin.allow: the hiring systems' hosts
 * and this job's own page). The app checks the address before every call, and CALL checks it again inside the page before anything
 * else, so a redirect between the two changes nothing. The script lives in the page under a name made from a random key, new each
 * time this screen opens, so a page that defines its own "UAplyAssist" (or writes the old window.__uaplyScan) gets nothing and cannot
 * put questions into UAply's question box. And the fill is handed only the profile items the scan saw the form ask for.
 */
public class AssistActivity extends AppCompatActivity {
    /** The one call into the page, as (CALL)({name, allow, act, p, j, mode}). Before anything else it reads the page's own address, which
     *  the page cannot fake (location is the browser's), calling no function the page could have replaced, and answers 'off' anywhere but
     *  an allowed https host; then 'none' while the script is not in the page yet. tools/test-assist-hostile.js runs this very text. */
    static final String CALL = "(function(C){var h=location.hostname,a=C.allow||[],ok=false;if(location.protocol==='https:')for(var i=0;i<a.length;i++)if(a[i]===h)ok=true;if(!ok)return 'off';var E=window[C.name];if(!E||typeof E.run!=='function')return 'none';return E.run(C)})";
    private static final int PICK_FILE = 41;
    private final String key = newKey();   // the name the script lives under in the page: random, new every time this screen opens
    private WebView web;
    private final Handler tick = new Handler(Looper.getMainLooper());
    private String lastReport = null;
    private boolean finished = false;
    private boolean scanMode = false;   // the bridge's first pass: read the form behind a cover, return its questions
    private long scanDeadline = 0;
    private ValueCallback<Uri[]> pendingChooser = null;
    private WebChromeClient.FileChooserParams pendingParams = null;

    @SuppressLint("SetJavaScriptEnabled")
    @Override
    protected void onCreate(Bundle saved) {
        super.onCreate(saved);
        String url = getIntent().getStringExtra("url");
        String co = getIntent().getStringExtra("co");
        scanMode = getIntent().getBooleanExtra("scan", false);
        scanDeadline = System.currentTimeMillis() + 25000;   // a form that never appears: the app opens it as it is

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        LinearLayout bar = new LinearLayout(this);
        bar.setOrientation(LinearLayout.HORIZONTAL);
        bar.setGravity(Gravity.CENTER_VERTICAL);
        bar.setBackgroundColor(Color.parseColor("#2A1218"));
        int pad = (int) (12 * getResources().getDisplayMetrics().density);
        bar.setPadding(pad, pad / 2, pad / 2, pad / 2);
        TextView title = new TextView(this);
        title.setText(scanMode ? "Reading " + (co == null || co.isEmpty() ? "the employer" : co) + "'s form..." : co == null || co.isEmpty() ? "Applying on the employer's page" : "Applying at " + co);
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
        android.widget.FrameLayout stack = new android.widget.FrameLayout(this);
        stack.addView(web, new android.widget.FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        if (scanMode) {   // the page lays out underneath (the scan needs real sizes) while the person sees this
            TextView cover = new TextView(this);
            cover.setText("Reading the application form so UAply can ask you anything your profile does not answer...");
            cover.setGravity(Gravity.CENTER);
            cover.setTextSize(16);
            cover.setPadding(pad * 2, pad * 2, pad * 2, pad * 2);
            cover.setBackgroundColor(Color.WHITE);
            cover.setTextColor(Color.parseColor("#2A1218"));
            stack.addView(cover, new android.widget.FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        }
        root.addView(stack, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1));
        setContentView(root);
        web.loadUrl(url);
        tick.postDelayed(this::poll, 1500);
    }

    private static String newKey() {
        byte[] b = new byte[16];
        new java.security.SecureRandom().nextBytes(b);
        StringBuilder s = new StringBuilder();
        for (byte x : b) s.append(String.format(java.util.Locale.ROOT, "%02x", x));
        return s.toString();
    }

    /** the page in front is https on an allowed host (checked again inside the page by CALL, so a redirect in between changes nothing) */
    private boolean onAllowedHost() {
        if (web == null) return false;
        String u = web.getUrl();
        if (u == null) return false;
        Uri p = Uri.parse(u);
        String h = p.getHost();
        return "https".equals(p.getScheme()) && h != null && AssistPlugin.allow.contains(h.toLowerCase(java.util.Locale.ROOT));
    }

    /** CALL with one request: "ask" (what the page shows), or "scan" / "fill" with the profile items to use */
    private String call(String act, String profile) {
        try {
            JSONObject c = new JSONObject();
            c.put("name", "__uaplyAssist_" + key);
            c.put("allow", new org.json.JSONArray(AssistPlugin.allow));
            c.put("act", act);
            if (profile != null) {
                c.put("p", new JSONObject(profile));
                c.put("j", new JSONObject(AssistPlugin.jobJson));
                c.put("mode", AssistPlugin.mode);
            }
            return CALL + "(" + c.toString() + ")";
        } catch (Exception e) {
            return "'off'";
        }
    }

    /** puts the assist script into the page, under this screen's key, once per document; only on an allowed host */
    private void inject() {
        if (web == null || AssistPlugin.engine.isEmpty() || !onAllowedHost()) return;
        web.evaluateJavascript(call("ask", null), v -> {
            if (web != null && "\"none\"".equals(v) && onAllowedHost())
                web.evaluateJavascript("(function(__uaplyAssistKey){" + AssistPlugin.engine + "\n})('" + key + "')", null);
        });
    }

    /** the page's state every 1.5 s: the confirmation page ends it; a form not yet filled at this address gets filled, once */
    private void poll() {
        if (finished || web == null) return;
        if (!onAllowedHost()) {   // another site (a redirect, a link the person tapped): nothing is asked of it or put into it
            if (scanMode && System.currentTimeMillis() > scanDeadline) { finishScan("{\"questions\":[]}"); return; }
            tick.postDelayed(this::poll, 1500);
            return;
        }
        web.evaluateJavascript(call("ask", null), v -> {
            try {
                if (v == null || v.equals("null") || v.equals("\"off\"")) {
                    if (scanMode && System.currentTimeMillis() > scanDeadline) finishScan("{\"questions\":[]}");
                    return;
                }
                if (v.equals("\"none\"")) { inject(); return; }
                JSONObject o = new JSONObject(new JSONObject("{\"s\":" + v + "}").getString("s"));
                if (!o.isNull("rep")) lastReport = o.optString("rep");
                if (o.optBoolean("c")) {   // the employer's confirmation page: leave it on screen a moment, then report Sent
                    finished = true;
                    final String at = o.optString("url");
                    tick.postDelayed(() -> { finished = false; done(true, at); }, 2500);
                    return;
                }
                if (scanMode) {   // the bridge: read the form once, hand its questions back, change nothing
                    if (!o.isNull("scan")) { finishScan(o.optString("scan")); return; }
                    if (System.currentTimeMillis() > scanDeadline) { finishScan("{\"questions\":[]}"); return; }
                    if (!o.optBoolean("ran") && o.optInt("n") > 3) scan();
                    return;
                }
                if (!o.optBoolean("ran") && o.optInt("n") > 3) fill();
            } catch (Exception ignored) {
            } finally {
                if (!finished) tick.postDelayed(this::poll, 1500);
            }
        });
    }

    /** the bridge's first pass: the scan lists what the profile cannot answer (with each question's kind and choices) and which profile
     *  items the form asks for; it is given stand-ins for the person's details, not the details (uaply-nav.js, assistShape) */
    private void scan() {
        if (!onAllowedHost()) return;
        web.evaluateJavascript(call("scan", AssistPlugin.profileJson), null);
    }

    private void finishScan(String json) {
        if (finished) return;
        finished = true;
        tick.removeCallbacksAndMessages(null);
        Intent r = new Intent();
        r.putExtra("confirmed", false);
        r.putExtra("scan", json == null ? "{\"questions\":[]}" : json);
        setResult(RESULT_OK, r);
        if (web != null) { web.stopLoading(); web.destroy(); web = null; }
        finish();
    }

    /** fills the form once at this address with what the scan saw it ask for (a call argument, never a page global), dropped after */
    private void fill() {
        if (!onAllowedHost()) return;
        web.evaluateJavascript(call("fill", AssistPlugin.profileJson), null);
    }

    /** the page's own resume box: offer the resume the person keeps in UAply first (only on an allowed host, and only when the scan saw
     *  the form take one) */
    private void chooseFile(ValueCallback<Uri[]> cb, WebChromeClient.FileChooserParams params) {
        if (pendingChooser != null) pendingChooser.onReceiveValue(null);
        pendingChooser = cb;
        pendingParams = params;
        String name = null;
        if (!scanMode && onAllowedHost())
            try { JSONObject r = new JSONObject(AssistPlugin.profileJson).optJSONObject("resume"); if (r != null && r.has("b64")) name = r.optString("name", null); } catch (Exception ignored) {}
        AlertDialog.Builder b = new AlertDialog.Builder(this).setTitle("Attach a file");
        if (name != null) b.setMessage("Your UAply resume: " + name).setPositiveButton("Use my UAply resume", (d, w) -> giveResume());
        b.setNeutralButton("Choose another file", (d, w) -> pickOther());
        b.setNegativeButton("Cancel", (d, w) -> answerChooser(null));
        b.setOnCancelListener(d -> answerChooser(null));
        b.show();
    }

    private void giveResume() {
        if (scanMode || !onAllowedHost()) { answerChooser(null); return; }   // the page may have moved to another site while the choice was open
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
