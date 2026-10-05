"""
Deploy the FoodBridge ML service to a FREE Hugging Face Docker Space.

  pip install huggingface_hub
  huggingface-cli login                      # paste a token with *write* access (hf.co/settings/tokens)
  python deploy/deploy_hf_space.py --space <your-hf-username>/foodbridge-ml \
         --django-url https://foodbridge-api.onrender.com/api --service-key <SERVICE_API_KEY from Render>

Creates/updates the Space, uploads ml_service + trained artifacts + dataset sample (LFS handled
automatically) and stores the shared key as a Space secret. The Space builds in ~5-10 minutes; then
the service is at https://<user>-foodbridge-ml.hf.space (Swagger: /docs).
"""
import argparse
import shutil
import tempfile
from pathlib import Path

from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parents[1]
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache", "tests")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--space", required=True, help="username/space-name")
    ap.add_argument("--django-url", required=True, help="public Django API base, e.g. https://x.onrender.com/api")
    ap.add_argument("--service-key", required=True, help="same SERVICE_API_KEY as the Django service")
    ap.add_argument("--private", action="store_true")
    a = ap.parse_args()

    api = HfApi()
    api.create_repo(a.space, repo_type="space", space_sdk="docker", private=a.private, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        dst = Path(tmp)
        shutil.copytree(ROOT / "ml_service", dst / "ml_service", ignore=IGNORE)
        shutil.copytree(ROOT / "data", dst / "data", ignore=IGNORE)
        shutil.copytree(ROOT / "scripts", dst / "scripts", ignore=IGNORE)
        for f in ("Dockerfile", "README.md"):
            shutil.copy(ROOT / "deploy" / "hf_space" / f, dst / f)
        print("Uploading… (first upload includes the trained models)")
        api.upload_folder(repo_id=a.space, repo_type="space", folder_path=str(dst),
                          commit_message="Deploy FoodBridge ML service")
    api.add_space_secret(a.space, "SERVICE_API_KEY", a.service_key)
    api.add_space_variable(a.space, "DJANGO_API_URL", a.django_url.rstrip("/"))
    api.add_space_variable(a.space, "REQUIRE_SERVICE_KEY", "true")
    owner, name = a.space.split("/")
    url = f"https://{owner.lower()}-{name.lower().replace('_', '-')}.hf.space"
    print(f"\nDone. Build logs: https://huggingface.co/spaces/{a.space}\nService URL (after build): {url}\n"
          f"Next: set ML_SERVICE_URL={url} on Render and ML_URL={url} as a GitHub secret.")


if __name__ == "__main__":
    main()
