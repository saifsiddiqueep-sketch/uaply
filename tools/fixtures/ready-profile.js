// The made-up person the browser tests swipe as, with the least a swipe right needs to apply (READY_MIN in shared/uaply-nav.js, since
// October 21: a name, an email employers can reply to, and a phone number or a resume). Below it, a swipe right opens "Finish your
// profile first" and the card does not move, so a test that swipes must give its person this first. One definition for every test:
//   const { readyProfile } = require("./fixtures/ready-profile.js");
//   await ev(readyProfile());                          // the default person
//   await ev(readyProfile({ name: "Sam Rivera" }));    // with some fields changed
// Giving the minimum makes the profile the person's own, and then "Hide roles that do not match my target titles" (on by default) uses
// the title the example profile had: with thousands of postings only a few match, and a swiping test runs out of cards after a handful.
// So this person has no target title (every role shows) unless the test passes one: readyProfile({ title: "Data Analyst" }).
// The returned text runs in the top page; it fills the app frame's profile, saves it and redraws, and returns true.
const READY = { name: "Jordan Tester", email: "jordan.tester@example.com", phone: "+1 215 555 0100", title: "" };

function readyProfile(over) {
  const p = Object.assign({}, READY, over || {});
  return "(()=>{const w=document.querySelector('iframe').contentWindow,A=w.__uaply;if(!A)return false;" +
    "Object.assign(A.S.profile,{name:" + JSON.stringify(p.name) + ",email:" + JSON.stringify(p.email) + ",title:" + JSON.stringify(p.title) + ",custom:true});" +
    "A.S.profile.ext=Object.assign({},A.S.profile.ext,{phone:" + JSON.stringify(p.phone) + "}," + (p.title ? "{}" : "{titles:[]}") + ");A.save();A.renderAll();return true})()";
}

module.exports = { READY, readyProfile };
