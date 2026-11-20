# Changes
* 2026-11-19: channel pipeline created. Daily plan (owner's request): 2 Shorts + 1 long video.
  Music: original "Ottoman Dheemi" without snare clicks. First battle: Stalingrad (Operation Uranus).
* 2026-11-20: the 08:50 Short B upload hit the morning YouTube quota (quota resets 16:00 MY), so it was uploaded at 10:00 by the daily check.
  Fix: render moved to 17:30 MY; the upload task gets a 16:50 MY retry run that only uploads videos still missing for the battle on the out branch.
* 2026-11-20: YOUTUBE_UPLOAD_VIDEO uploads ended as "Can't process file"; re-uploaded Stalingrad with YOUTUBE_MULTIPART_UPLOAD_VIDEO and made the upload task use it and verify processing.
* 2026-11-20: GitHub's schedule did not start the 17:30 render, so it was dispatched by hand at 22:00. The cron is removed; the upload task's 16:50 run now dispatches daily.yml.
