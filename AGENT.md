# AGENT.md

## 1. プロジェクト目的
- Fixstars Amplify を用いたライブタイムテーブル最適化を、安全に運用できる形で提供する。
- 受け入れ条件は「最適解が出ない」以外でクラッシュしないこと。

## 2. コード編集時の原則
1. 変更は最小責務単位で行う。
2. 公開 API は型ヒントと docstring を付ける。
3. ユーザ向けエラー文言は原因と対処を含める。
4. `--debug` 以外で生トレースをユーザに見せない。

## 3. 責務分離の原則
- `cli.py`: 引数・終了コード・トップレベル例外制御。
- `pipeline.py`: load -> parse -> build -> solve -> validate -> output の連結。
- `qubo_builder.py`: QUBO/候補生成/solver 連携。
- `validator.py`: 解妥当性検証。
- `csv_parser.py`: 入力 CSV の中間表現化。
- `config.py`: 設定ロードと一貫性検証。
- `output.py`: stdout/CSV/JSON/MD 出力。

## 4. エラー処理方針
- 入力不備・設定不備・I/O 不備は `UserVisibleError` 派生例外へ正規化。
- 「解なし」は `NoFeasibleSolutionError` として正常停止（exit code 0）扱い可。
- 予期せぬ例外は CLI で捕捉し、非 debug では要点のみ表示。

## 5. テスト方針
- 正常系 + 主要失敗モードを pytest で維持。
- 最低限、設定・CSV・出力・solver 空解・token 未設定フォールバックを検証。

## 6. README 同期方針
- 設定項目追加時は README の「パラメータ説明」を同時更新。
- 入出力形式変更時は README のサンプルを更新。
- 既知の近似・未対応事項は README に必ず残す。

## 7. 新機能追加時チェックリスト
- [ ] モデル更新（`models.py`）
- [ ] 設定スキーマ更新（`config.py` + config sample）
- [ ] 入力パーサ更新（必要なら）
- [ ] 妥当性検証更新（`validator.py`）
- [ ] README 更新
- [ ] テスト追加

## 8. QUBO 変更時に必ず行う確認項目
- 変数定義が day/band/slot で一意か。
- 目的関数の符号（maximize/minimize 変換）が崩れていないか。
- 休憩・転換・不可時間制約と矛盾していないか。
- 空解・不正解を `validator.py` が弾けるか。

## 9. CSV パーザ差し替え時の注意点
- `ParsedAvailability` を維持し、呼び出し側の契約を壊さない。
- 列不足・型不正・時刻不正を必ず説明可能なエラーにする。
- `band_id` の必須/重複禁止は維持する。

## 10. マルチデイ対応時の注意点
- 日ごとのグリッド幅差異を前提に実装する。
- 日跨ぎ演算を避け、日単位の独立制約を優先。
- 出力ソートキーは `(day, start)` を維持する。
