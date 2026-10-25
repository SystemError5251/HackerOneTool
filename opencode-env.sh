# shellcheck shell=bash
# opencode-env.sh — offline lock for OpenCode, extracted from OPENCODE-LOCAL.
#
# Sourced by analyze.sh before starting OpenCode. Turns off every OpenCode
# feature that would reach the internet, so the AI layer stays inside the
# authorized scope and never phones home. The recon helpers (h1*.py) still
# talk to HackerOne's own public API — that is the tools' job and is not a
# target asset; this file only locks down OpenCode and the model layer.
export OPENCODE_DISABLE_AUTOUPDATE=1      # no update checks or notices
export OPENCODE_DISABLE_MODELS_FETCH=1    # do not download the models.dev catalogue
export OPENCODE_DISABLE_LSP_DOWNLOAD=1    # do not download language servers
export OPENCODE_DISABLE_DEFAULT_PLUGINS=1 # no built-in cloud auth plugins
export OPENCODE_DISABLE_CLAUDE_CODE=1     # ignore ~/.claude prompts and skills
export OPENCODE_AUTO_SHARE=false          # never auto-share a session

# Keep the local model server and OpenCode's own TUI server off any proxy.
# Without this, a configured HTTP(S) proxy (e.g. Burp on a pentest box)
# swallows the 127.0.0.1 call and OpenCode reports "Unexpected server error".
export NO_PROXY="localhost,127.0.0.1${NO_PROXY:+,$NO_PROXY}"
export no_proxy="$NO_PROXY"

# llama-server API key. Only needed when the model host is not 127.0.0.1.
export OCL_LLAMA_API_KEY="${OCL_LLAMA_API_KEY:-local-no-key}"
