# Verification

The change is accepted when:

- `knoar desktop-config read-form --json` returns the same form shape as `GET /config/form`.
- `knoar desktop-config write-form --json` writes `config.yaml` and returns `UiConfigUpdateResponse`.
- Desktop settings save does not call `/config` or `/config/form` from renderer `fetch`.
- Browser mode still saves through the existing HTTP API.
- CI-style lint and tests pass.

Verified locally:

- `.venv/bin/python -m ruff check src tests scripts`
- `.venv/bin/python -m unittest tests.test_desktop_config_cli tests.test_core_config tests.test_doctor tests.test_model_probe tests.test_ui_api tests.test_image_generation tests.test_chat_agent tests.test_chat_tool_flows tests.test_wiki_index_storage`
- `npm --prefix renderer run build`
- `npm --prefix desktop run build`
