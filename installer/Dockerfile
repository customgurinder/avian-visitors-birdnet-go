FROM python:3.12-slim

# git for fetching frontend + packs; Pillow for build_masks.py
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir Pillow==11.0.0

COPY install.sh /usr/local/bin/install.sh
COPY patch_stamps.py /usr/local/bin/patch_stamps.py
COPY patch_theme_toggle.py /usr/local/bin/patch_theme_toggle.py
RUN chmod +x /usr/local/bin/install.sh /usr/local/bin/patch_stamps.py /usr/local/bin/patch_theme_toggle.py

# git needs a home dir / safe.directory tolerance under arbitrary UIDs
ENV GIT_TERMINAL_PROMPT=0
RUN git config --system --add safe.directory '*'

ENTRYPOINT ["/usr/local/bin/install.sh"]
