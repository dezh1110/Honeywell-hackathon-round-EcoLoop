# Ubuntu 24.04 base to match the exact EnergyPlus build this project was
# verified against (see backend/README.md "Verified against real
# EnergyPlus" and SYSTEM_ARCHITECTURE.md §6) -- a slim/Debian base risks a
# glibc mismatch with the Ubuntu-targeted installer below.
FROM ubuntu:24.04

# EnergyPlus installer to bake in. Defaults to the exact build this project
# was tested against. Override with --build-arg ENERGYPLUS_INSTALLER_URL=...
# to use a different version -- check https://github.com/NREL/EnergyPlus/releases
# for official builds; this default uses a mirror that publishes the
# Ubuntu24.04 asset (NREL's own releases may not have one for older
# EnergyPlus versions).
ARG ENERGYPLUS_INSTALLER_URL="https://github.com/NatLabRockies/EnergyPlus/releases/download/v26.1.0/EnergyPlus-26.1.0-6f2e40d102-Linux-Ubuntu24.04-x86_64.sh"
ARG ENERGYPLUS_INSTALL_DIR="/usr/local/EnergyPlus-26-1-0"
ENV ENERGYPLUS_INSTALL_DIR=${ENERGYPLUS_INSTALL_DIR}

WORKDIR /srv/ecoloop

# EnergyPlus's binary links against X11/GL libraries even for headless,
# server-side use (no display is ever opened) -- confirmed by actually
# running this Dockerfile: without these, `pyenergyplus` fails to load with
# `OSError: libX11.so.6: cannot open shared object file`, not an error
# that's obvious from EnergyPlus's own documentation.
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-pip python3-venv curl ca-certificates \
        libx11-6 libxext6 libxrender1 libxrandr2 libxi6 \
        libsm6 libice6 libgl1 libglu1-mesa \
    && rm -rf /var/lib/apt/lists/*

# Install EnergyPlus. The installer is an interactive shell script; the
# printf sequence below answers its three prompts (accept license / confirm
# install directory / decline symlinks) -- this exact sequence was verified
# working, not guessed (a bare `yes` pipes "y" into the directory-path
# prompt too, which silently creates a directory literally named "y").
RUN mkdir -p ${ENERGYPLUS_INSTALL_DIR} && \
    curl -fsSL -o /tmp/energyplus_installer.sh "${ENERGYPLUS_INSTALLER_URL}" && \
    chmod +x /tmp/energyplus_installer.sh && \
    printf 'y\n\nn\n' | /tmp/energyplus_installer.sh --mode unattended --prefix ${ENERGYPLUS_INSTALL_DIR} && \
    rm -f /tmp/energyplus_installer.sh

COPY requirements.txt .
RUN pip install --no-cache-dir --break-system-packages -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/srv/ecoloop:${ENERGYPLUS_INSTALL_DIR}

CMD ["python3", "-m", "app.main"]
