# Historical direct-provider probe

`test_nvidia.py` is the early, developer-only direct-provider verification utility, retained for its offline protocol tests. It is not Recall's model gateway and is not part of judge setup or the application runtime. No direct-provider credentials belong in Recall's environment template. Configure provider credentials in Nightshift; the supported path is `app/adapters/nightshift.py`.

`backend/scripts/test_nightshift.py` reuses only the image-format helpers from this historical module. Importing it makes no requests. Production agents never import it.
