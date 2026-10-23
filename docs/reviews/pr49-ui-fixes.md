# PR #49 review: proposed sign-up card fixes for Mohammed (shared/uaply-signup.js)

October 22, 2026. Reviewer 2 (security and races). The server-side findings are fixed on `bot2-signin-fixes`. These two are in
`shared/uaply-signup.js`, which is Mohammed's, so they are proposed here as exact patches and are not applied. Line numbers are those
of origin/sandbox 6552edf (after PR #50).

## Finding 5 (what PR #50 left): signing in to an existing account on a device that holds someone else's profile

PR #50's `claimDevice()` gives a new account on a shared device a clean profile. A sign-in to an account that already exists does not
call it. So when person B signs in (code or Google) on a phone where person A's profile is saved, B's applications go out with A's
email, phone, resume and saved answers. UAply keeps the profile on the device only, so nothing on the server would ever correct it.

Proposed: run the same check for every sign-in, and ask before clearing (A's details live only on this device, so B should choose).

```diff
@@ line 607, the code sign-in that worked
-          else{if(kind==="up")saveName(V.first,V.last,user.email,true);V.view="signedin";B.signedIn(user);render(true)}
+          else{
+            if(otherProfile(user.email)&&!w.confirm("This device holds another person's profile. Start fresh for "+user.email+"? (Their details are kept only on this device.)")){
+              B.signedIn(user);V.view="signedin";render(true);return;   /* keeps it, as asked; the Account screen shows whose profile it is */
+            }
+            claimDevice(user.email);if(kind==="up")saveName(V.first,V.last,user.email,true);V.view="signedin";B.signedIn(user);render(true)
+          }
@@ line 651, back from Google to an account that already existed
     if(!V.isNew){
+      if(otherProfile(user.email)&&w.confirm("This device holds another person's profile. Start fresh for "+user.email+"? (Their details are kept only on this device.)"))claimDevice(user.email);
       if(pend.first&&pend.last)saveName(pend.first,pend.last,user.email,true);
@@ after claimDevice()
+  /* the device's saved profile belongs to a different email than the one now signed in */
+  function otherProfile(email){
+    email=String(email||"").toLowerCase();var p=A.S.profile||{},pe=p.custom?String(p.email||"").toLowerCase():"",oe=String(ownGet().email||"").toLowerCase();
+    return !!email&&((pe&&pe!==email)||(!pe&&oe&&oe!==email));
+  }
```

A styled sheet would fit the card better than `w.confirm`. The rule is what matters: never send applications for B with A's details
without asking. Test: in `tools/ui-signup.js`, sign out of account A with a saved phone, sign in as B with a code, and expect the
question, then B's profile with an empty phone after "Start fresh".

## Finding 6: the name typed before "Continue with Google" goes to whichever Google account comes back

`startAfterGoogle()` (lines 645-657) uses the name the person typed on the card (kept in this tab's sessionStorage for 15 minutes),
whatever Google account then signs in. If someone typed "Sam Rivera / sam@x.com", pressed Google and picked a different Google account
(a partner's on a shared phone), that account gets Sam's name. The email the person typed is right there to compare.

```diff
@@ line 649
-    if(!V.first&&!V.last){V.first=pend.first||"";V.last=pend.last||""}
+    /* the typed name belongs to the typed email: use it only when Google signed in that same address (or none was typed) */
+    var sameOne=!pend.email||String(pend.email).toLowerCase()===String(user.email||"").toLowerCase();
+    if(!sameOne){pend=Object.assign({},pend,{first:"",last:""})}
+    if(!V.first&&!V.last){V.first=pend.first||"";V.last=pend.last||""}
```

With `sameOne` false, `V.typedName` stays false, so the questions ask for the name (the existing "name" step). Test: in
`tools/ui-signup.js`, type a name and `a@gmail.com`, then sign in with the stand-in Google as `b@gmail.com`, and expect the name
question with empty boxes rather than a saved name.
