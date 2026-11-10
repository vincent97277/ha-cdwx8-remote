# 安裝久豪 CDWX8 遙控器

需要 Home Assistant Core 2026.10.2 或更新版本、已啟用的 Bluetooth 整合，以及可提供原始 BLE 廣播的接收器。可使用相容的本機藍牙介面或藍牙代理器。已在 Core 2026.10.2 和內建 Intel 藍牙的主機驗證。 [Home Assistant Bluetooth](https://www.home-assistant.io/integrations/bluetooth/)

## 使用 HACS

1. 用 [My Home Assistant 連結](https://my.home-assistant.io/redirect/hacs_repository/?owner=vincent97277&repository=ha-cdwx8-remote&category=integration) 開啟 HACS。也可以在 **HACS → ⋮ → 自訂儲存庫（Custom repositories）** 貼上 `https://github.com/vincent97277/ha-cdwx8-remote`，類型選 **Integration**。
2. 搜尋 **Jiuhao CDWX8 Remote**，選擇 **Download** 下載，然後重啟 Home Assistant。

如果之前已手動安裝同一個 `cdwx8` 整合，可直接在 HACS 下載新版並重啟，沿用既有的遙控器和自動化。 [HACS 自訂儲存庫](https://www.hacs.xyz/docs/faq/custom_repositories/)

## 手動安裝

在 [GitHub Releases](https://github.com/vincent97277/ha-cdwx8-remote/releases) 下載所需版本的 ZIP 原始碼並解壓縮。將其中的 `custom_components/cdwx8` 資料夾複製到 Home Assistant 設定目錄的 `custom_components/` 下。HA OS 的 `manifest.json` 應位於 `/config/custom_components/cdwx8/manifest.json`。複製後重啟 Home Assistant。

## 按一下新增遙控器

1. 在 **設定 → 裝置與服務 → 增加整合** 搜尋 **Jiuhao CDWX8 Remote**。若遙控器已出現在「已發現」，可以直接開啟該卡片。
2. 選 **按鍵自動偵測**，或依已發現卡片的提示開始。畫面出現掃描提示後，在 30 秒內按一下要加入的遙控器的任一實體鍵。
3. 核對偵測到的 MAC，確認新增。HA 會一併儲存按鍵廣播中的 UUID 前綴。

要加入第二支，重新開啟新增流程並按第二支。每個不同的廣播 MAC 都有自己的設定項目與按鍵。同一個 MAC 只能加入一次。兩支分開加入的流程已用不同 MAC 的封包重播驗證。

## 綁定自動化

在自動化編輯器選擇「收到事件」觸發。目標選該支遙控器的 **Button A**、**Button B**、**Button C** 或 **Button D** 事件實體，事件類型選 `single_press`。也可以選共用的 **Button** 事件實體，再以 `button_a` 到 `button_d` 區分按鍵。 [Home Assistant 事件觸發](https://www.home-assistant.io/triggers/event.received/)

在遙控器裝置頁點 **按下 A** 至 **按下 D**，即可模擬實體按壓。這些 `button.*` 實體也可以放到儀表板。 [Home Assistant 按鈕實體](https://www.home-assistant.io/integrations/button/)

## 偵測逾時

將遙控器移近接收器，選 **重新偵測** 後再按一下。如果仍然逾時，在 HA 藍牙廣播監視器核對按鍵時是否收到原始封包，以及 MAC 是否已存在於已設定的裝置中。 [藍牙廣播監視器](https://www.home-assistant.io/integrations/bluetooth/#advertisement-monitor)

也可以選 **手動輸入**，填寫遙控器廣播的 MAC 和按鍵封包中的六位元組 UUID 前綴。這個前綴是 128-bit Service UUID 在原始廣播順序的前六個位元組。若工具顯示的是帶連字號的標準 UUID，先將完整 16 個位元組反序，再取前六個。
