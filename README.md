# Hello CGPAR — Updated

Updated from the supplied final version.

### Updates
- Existing student eligibility/list remains supported.
- Student IDs not found in `students.json` can now be entered manually with a new name and generated without the old automatic rejection.
- School → Major dependent dropdown added.
- Added all requested school-wise majors.
- Letter sentence updated to: “...is about to complete his/her bachelor with a major in [Major] from the [School] of IUB.”
- One blank line above the authorized official name was removed from the Word templates to reduce unnecessary page overflow.
- Existing company database, GitHub persistence, Word/PDF export and other functionality retained.

### Run
```bash
pip install -r requirements.txt
streamlit run app.py
```

### Major list
The complete requested School → Major mapping is built into `app.py`.
