# CDWX8 開發與測試

在本 repo 根目錄用 Python 3.14.6 建立測試環境：

```bash
python3.14 -m venv .venv
.venv/bin/python -m pip install -r tests/requirements.txt
.venv/bin/python -m pytest
```

測試將目前 checkout 的整合載入隔離的 Home Assistant Core，重播合成 BLE 封包。涵蓋兩支遙控器獨立新增與事件分流、廣播去重、掃描逾時和虛擬按鈕。測試透過 HA 的藍牙接收入口注入封包，毋須連線實機。

GitHub Actions 在 push 和 PR 執行相同測試，並執行 HACS 與 Hassfest 驗證。發布時確認三項檢查通過，再從通過的提交建立 GitHub Release。Release 標籤版本應與 `custom_components/cdwx8/manifest.json` 一致。
