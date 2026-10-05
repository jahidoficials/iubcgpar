# Hello CGPAR — Add New Company Persistence Setup (Free)

This version adds **➕ Add New Company** to each Company dropdown.

When a user saves a new company:
1. The company becomes available immediately in the current session.
2. The app uses the GitHub Contents API to update `companies.json` in the repository.
3. The GitHub commit becomes the persistent source for later users and future Streamlit restarts/redeploys.

## Files changed

- `app.py` — Add New Company UI + GitHub persistence
- `requirements.txt` — adds `requests`

## 1. Upload the updated files to GitHub

In your GitHub repository:

1. Open the repository used by the Streamlit app.
2. Replace/upload the updated `app.py`.
3. Replace/upload the updated `requirements.txt`.
4. Keep your existing `companies.json`, `students.json`, templates, fonts, and `packages.txt`.
5. Commit the changes to the branch used by Streamlit (normally `main`).

## 2. Create a fine-grained GitHub token

1. GitHub → profile picture → **Settings**.
2. Left sidebar → **Developer settings**.
3. **Personal access tokens** → **Fine-grained tokens**.
4. Click **Generate new token**.
5. Token name: e.g. `HelloCGPAR Company Writer`.
6. Choose an expiration you are comfortable with. If the token expires, create a new one and replace it in Streamlit Secrets.
7. **Resource owner**: select the account that owns the repository.
8. **Repository access** → **Only select repositories**.
9. Select only the repository that runs Hello CGPAR.
10. Under **Repository permissions**, find **Contents** and choose **Read and write**.
11. Keep other permissions at their minimum/default values unless GitHub requires metadata read access automatically.
12. Click **Generate token**.
13. Copy the token immediately.

IMPORTANT: Never paste this token inside `app.py`, `companies.json`, README, or any GitHub file.

## 3. Find the repository value

If your GitHub repository URL looks like:

`https://github.com/yourusername/hello-cgpar`

then use:

`GITHUB_REPO = "yourusername/hello-cgpar"`

Do not include `https://github.com/` and do not include `.git`.

## 4. Add Secrets in Streamlit Community Cloud

Open Streamlit Community Cloud and open your Hello CGPAR app.

1. Open the app's menu/settings.
2. Go to **App settings** / **Settings**.
3. Open **Secrets**.
4. Paste the following, replacing only the example values:

```toml
GITHUB_TOKEN = "github_pat_PASTE_YOUR_REAL_TOKEN_HERE"
GITHUB_REPO = "YOUR_GITHUB_USERNAME/YOUR_REPOSITORY_NAME"
GITHUB_BRANCH = "main"
GITHUB_COMPANIES_PATH = "companies.json"
```

5. Click **Save**.

If your default deployment branch is not `main`, replace `main` with the exact branch name.

If `companies.json` is inside a folder, use its repository path, for example:

```toml
GITHUB_COMPANIES_PATH = "HelloCGPAR/companies.json"
```

For the supplied project structure, `companies.json` is beside `app.py`, so `companies.json` is normally correct.

## 5. Test it

1. Open the online app.
2. Go to **3. Internship Organization(s)**.
3. Open **Company** dropdown.
4. Select **➕ Add New Company**.
5. Enter a new company name.
6. Enter at least one address line.
7. Click **Save New Company**.
8. The new company should become selected and its address should appear.
9. Open GitHub → repository → `companies.json` and confirm the new company was committed there.
10. Reopen/restart the app and confirm the company remains available in the dropdown.

## What remains unchanged

The existing app features remain available: student eligibility check, editable student name, gender handling, School selection, Authorized Official selection, letter date, internship start month, multiple companies, auto-filled editable addresses, duplicate company validation, live preview, DOCX output, and PDF output.

## If saving fails

- `401`: token is invalid/expired or copied incorrectly.
- `403`: token does not have permission, repository policy blocks it, or the selected repository is wrong.
- `404`: `GITHUB_REPO`, branch, or `GITHUB_COMPANIES_PATH` is wrong, or the token cannot access that repository.
- `409/422`: repository/branch state changed or the API rejected the update; retry after refreshing the app and check the repository settings.

## Security

Use a fine-grained token limited to only this repository. Do not commit the token to GitHub. Keep it only in Streamlit Secrets. If the token is ever exposed publicly, revoke it in GitHub immediately and create a new one.
