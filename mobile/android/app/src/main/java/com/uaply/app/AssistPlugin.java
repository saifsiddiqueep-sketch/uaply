package com.uaply.app;

import android.content.Intent;

import androidx.activity.result.ActivityResult;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.ActivityCallback;
import com.getcapacitor.annotation.CapacitorPlugin;

/**
 * Assisted apply (docs/assisted-apply.md): the web app calls Capacitor.Plugins.UAplyAssist.open({url, engine, profile, job, system, mode})
 * from "Finish applying on their site" (shared/uaply-nav.js, assistedApply). This opens the employer's own application page in
 * {@link AssistActivity}, which puts shared/uaply-assist.js (passed in as text, so the app always runs the version the site serves)
 * into the page, fills it from the person's profile, attaches their resume, and stops at "Review and tap Submit".
 * It resolves {confirmed, url, report}: confirmed is true only when the employer's confirmation page appeared, and only then does
 * the Job Tracker say Sent.
 */
@CapacitorPlugin(name = "UAplyAssist")
public class AssistPlugin extends Plugin {

    /** what the activity needs; kept here rather than in the Intent, since a resume can be bigger than an Intent may carry */
    static String engine = "";
    static String profileJson = "{}";
    static String jobJson = "{}";
    static String mode = "assisted";

    @PluginMethod
    public void open(PluginCall call) {
        String url = call.getString("url", "");
        if (url == null || !url.startsWith("https://")) { call.reject("An https address is needed"); return; }
        String eng = call.getString("engine", "");
        if (eng == null || !eng.contains("UAplyAssist")) { call.reject("The assist script is missing"); return; }
        JSObject profile = call.getObject("profile", new JSObject());
        JSObject job = call.getObject("job", new JSObject());
        engine = eng;
        profileJson = profile == null ? "{}" : profile.toString();
        jobJson = job == null ? "{}" : job.toString();
        /* "automatic" only when the web app passed it (shared/assist-systems.json: counsel_approved and no human check measured); the
           page check happens again in the page itself (UAplyAssist.submitIfAllowed) */
        mode = "automatic".equals(call.getString("mode", "assisted")) ? "automatic" : "assisted";
        Intent i = new Intent(getContext(), AssistActivity.class);
        i.putExtra("url", url);
        i.putExtra("co", job == null ? "" : job.getString("co", ""));
        i.putExtra("scan", Boolean.TRUE.equals(call.getBoolean("scan", false)));   // the bridge: read the form, change nothing, return its questions
        startActivityForResult(call, i, "assistDone");
    }

    @ActivityCallback
    private void assistDone(PluginCall call, ActivityResult result) {
        if (call == null) return;
        Intent data = result.getData();
        JSObject ret = new JSObject();
        ret.put("confirmed", data != null && data.getBooleanExtra("confirmed", false));
        ret.put("url", data == null ? "" : data.getStringExtra("url"));
        ret.put("report", data == null ? null : data.getStringExtra("report"));
        String scan = data == null ? null : data.getStringExtra("scan");
        if (scan != null) {   // {questions:[{q,key,kind,opts,required}], seen, filled} from UAplyAssist.scan
            try {
                JSObject sc = new JSObject(scan);
                ret.put("questions", sc.has("questions") ? sc.getJSONArray("questions") : new com.getcapacitor.JSArray());
                ret.put("seen", sc.optInt("seen"));
                ret.put("filled", sc.optInt("filled"));
            } catch (Exception e) { ret.put("questions", new com.getcapacitor.JSArray()); }
        }
        if (scan == null) { engine = ""; profileJson = "{}"; }   // the profile and resume do not stay in memory after the form closes
        call.resolve(ret);
    }
}
