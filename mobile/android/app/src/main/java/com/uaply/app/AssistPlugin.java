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
 * Assisted apply (docs/assisted-apply.md): the web app calls Capacitor.Plugins.UAplyAssist.open({url, engine, allow, profile, job,
 * system, mode, scan}) from "Finish applying on their site" (shared/uaply-nav.js, assistedApply). This opens the employer's own
 * application page in {@link AssistActivity}, which puts shared/uaply-assist.js (passed in as text, so the app always runs the version
 * the site serves) into the page, fills it, attaches the resume, and stops at "Review and tap Submit".
 * allow: the hosts of the hiring systems (shared/assist-systems.json); the job's own page's host is added here. Nothing is ever put into
 * a page on any other host. profile: for the scan, stand-ins for the person's details (uaply-nav.js, assistShape); for the fill, only
 * what the scan saw the form ask for (assistOnly), never the whole profile.
 * It resolves {confirmed, url, report}: confirmed is true only when the employer's confirmation page appeared, and only then does
 * the Job Tracker say Sent. A scan resolves {questions, seen, filled, keys, answerKeys, resume}.
 */
@CapacitorPlugin(name = "UAplyAssist")
public class AssistPlugin extends Plugin {

    /** what the activity needs; kept here rather than in the Intent, since a resume can be bigger than an Intent may carry */
    static String engine = "";
    static String profileJson = "{}";
    static String jobJson = "{}";
    static String mode = "assisted";
    static java.util.Set<String> allow = new java.util.HashSet<>();

    @PluginMethod
    public void open(PluginCall call) {
        String url = call.getString("url", "");
        if (url == null || !url.startsWith("https://")) { call.reject("An https address is needed"); return; }
        String eng = call.getString("engine", "");
        if (eng == null || !eng.contains("UAplyAssist")) { call.reject("The assist script is missing"); return; }
        JSObject profile = call.getObject("profile", new JSObject());
        JSObject job = call.getObject("job", new JSObject());
        java.util.Set<String> hosts = new java.util.HashSet<>();
        String start = android.net.Uri.parse(url).getHost();
        if (start != null && !start.isEmpty()) hosts.add(start.toLowerCase(java.util.Locale.ROOT));   // this job's own page, and only this job's
        com.getcapacitor.JSArray given = call.getArray("allow", new com.getcapacitor.JSArray());
        for (int k = 0; given != null && k < given.length(); k++) {
            String h = given.optString(k, "").toLowerCase(java.util.Locale.ROOT);
            if (h.matches("[a-z0-9-]+(\\.[a-z0-9-]+)+")) hosts.add(h);
        }
        allow = hosts;
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
        if (scan != null) {   // {questions:[{q,key,kind,opts,required}], seen, filled, keys, answerKeys, resume} from the scan
            try {
                JSObject sc = new JSObject(scan);
                ret.put("questions", sc.has("questions") ? sc.getJSONArray("questions") : new com.getcapacitor.JSArray());
                ret.put("seen", sc.optInt("seen"));
                ret.put("filled", sc.optInt("filled"));
                ret.put("keys", sc.optJSONArray("keys") != null ? sc.optJSONArray("keys") : new com.getcapacitor.JSArray());
                ret.put("answerKeys", sc.optJSONArray("answerKeys") != null ? sc.optJSONArray("answerKeys") : new com.getcapacitor.JSArray());
                ret.put("resume", sc.optBoolean("resume", false));
            } catch (Exception e) { ret.put("questions", new com.getcapacitor.JSArray()); }
        }
        engine = "";            // nothing stays in memory after the form closes (the next open passes all of it again)
        profileJson = "{}";
        allow = new java.util.HashSet<>();
        call.resolve(ret);
    }
}
