Repo baseline (legacy and unfamiliar repos):
- If `.claude/project-profile.md` exists, read it first. It records this repo's layout, conventions and known debt. Judge the change against *this repo's* conventions, not an ideal architecture or the newest framework idiom.
- New code should follow the existing conventions, except those the profile lists as known debt. Copying a debt pattern into new code is a finding. Not modernising old code is not.
- Report problems in code the diff didn't touch under "Pre-existing (not blocking)", at most 3, so legacy debt isn't blamed on the change.
- If there is no project profile, infer the conventions from the touched files' neighbours, and say in one line that `/onboard-repo` would make reviews of this repo more accurate.
