# TimeTable_Amplify

まず最初に編集する場所（利用者向け）:
1. `configs/default_config.json`（日程・休憩・転換・重み）
2. `input/example_availability_editable.json`（出演可能時間・編集用中間ファイル）
3. 必要なら `src/timetable_amplify/qubo_builder.py`（報酬・制約ロジック）

## 1. プロジェクト概要
Fixstars Amplify ベースでライブのタイムテーブルを最適化する Python 3.11+ プロジェクトです。  
安全性重視で「最適解がない」以外の失敗は、入力検証エラーまたは安全停止として扱います。

## 2. できること / まだ未対応
### できること
- 複数日程データ構造
- 5分グリッドなど可変グリッド
- 休憩回数・休憩長・転換長の設定
- 出演可能/出演不可時間を考慮
- 解の妥当性検証（重複/転換/休憩/時間帯/不可時間）
- `AMPLIFY_TOKEN` 未設定時の安全フォールバック

### 未対応（現時点制約）
- Amplify SDK への厳密 BQM 投入（統合ポイントは実装済み）
- 厳密最適化保証
- CSV 仕様の高度化（複数候補窓や日跨ぎ精密表現）

## 3. ディレクトリ構成
```text
TimeTable_Amplify/
├── AGENT.md
├── README.md
├── pyproject.toml
├── configs/
│   ├── default_config.json
│   └── multiday_config.json
├── input/
│   ├── example_availability_editable.json
│   └── example_multiday_availability_editable.json
├── csv_example/
│   ├── 8月ライブ出演可能時間フォーム（回答） - 一覧.csv
│   └── 二入卒業ライブ_出演可能時間フォーム（回答） - 一覧.csv
├── tests/
│   ├── test_failure_modes.py
│   └── test_self_check.py
└── src/timetable_amplify/
    ├── cli.py
    ├── main.py
    ├── config.py
    ├── csv_parser.py
    ├── errors.py
    ├── logging_utils.py
    ├── models.py
    ├── output.py
    ├── pipeline.py
    ├── qubo_builder.py
    ├── qubo.py
    ├── time_utils.py
    └── validator.py
```

## 4. 必要環境
- Python 3.11+
- （任意）Fixstars Amplify SDK

## 5. セットアップ手順
```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## 6. Amplify トークン設定方法
```bash
export AMPLIFY_TOKEN=your_token_here
```
- `solver.strict_optimal=false` なら未設定でもフォールバック実行
- `solver.strict_optimal=true` なら明示エラーで停止

## 7. 実行方法
```bash
python -m timetable_amplify.main --config configs/default_config.json
python -m timetable_amplify.main --config configs/default_config.json --debug
```

## 8. サンプル入力
- `input/example_availability_editable.json`: 単日サンプル（中間ファイル）
- `input/example_multiday_availability_editable.json`: 複数日サンプル（中間ファイル）
- `csv_example/*.csv`: Googleフォーム由来の元CSVサンプル

## 9. 出力ファイル説明
- `output/*.csv`: 日時・ラベル一覧
- `output/*.json`: 目的値・診断情報を含む機械可読形式
- `output/*.md`: レポート用途
- 標準出力: 人間向けタイムテーブル

## 10. パラメータ説明
- グリッド幅: `event_days[].grid_minutes`
- 日程: `event_days[]`
- 休憩回数: `event_days[].breaks[].count`
- 休憩長: `event_days[].breaks[].duration_minutes`
- 転換長: `event_days[].changeover_minutes`
- ブロック価値傾斜: `reward.block_base_values`, `reward.block_step`, `reward.intra_step`
- ブロック人数均等化重み: `reward.balance_penalty`（将来の厳密QUBO強化で利用）
- 目的関数/制約重み: `reward.*`, `penalties.*`

## 11. 出演可能時間の取り込み仕様（CSV -> 中間ファイル）
### 運用フロー
1. Googleフォーム形式CSVをCLIで読み込んで中間ファイルJSONを生成
2. 生成されたJSONを人間が手編集（備考の反映や overrides 追記）
3. 最適化はJSONのみを参照（元CSVは直接読まない）

```bash
python -m timetable_amplify.main --generate-editable-from-csv "csv_example/8月ライブ出演可能時間フォーム（回答） - 一覧.csv" --editable-out input/generated_availability_editable.json
```

### 中間ファイル（編集対象）
- `schema_version`
- `generated_from`
- `grid_minutes`
- `days[]`: day番号/ラベル/観測時台
- `bands[]`
  - `name`
  - `slot_minutes`
  - `availability_by_day_hour`（True/False）
  - `notes_by_day`（備考原文）
  - `overrides`（例: `[{"day": 1, "allow_until": "14:30"}]`）

### CSV値の正規化ルール
- `出演可` => `true`
- `出演不可` => `false`
- 空欄/その他 => warning を出して `false` 扱い
- `出演枠` は `15分枠` のような文字列から数値抽出

## 12. エラー時の確認ポイント
1. 設定ファイルが存在するか
2. JSON 型が正しいか
3. 時刻文字列が `HH:MM` か
4. duration がグリッドで割り切れるか
5. 開始/終了時刻の順序が正しいか
6. 休憩長・転換長が正か
7. CSV 列が足りているか
8. `band_id` が空/重複していないか
9. 出力先がディレクトリとして作成可能か
10. `AMPLIFY_TOKEN` が必要条件を満たすか

## 13. よくある失敗
- `CSV missing columns`: ヘッダ不足
- `invalid start/end time`: HH:MM 形式不正
- `duration ... is not divisible by grid`: グリッド不整合
- `NO_SOLUTION`: 制約が強すぎるか時間窓が狭すぎる

## 14. 開発者向けメモ
- トップレベル例外は `cli.py` に集約
- 妥当性検証は `validator.py` を単一責務で維持
- solver 変更時も `SolveResult` 契約を維持

## 15. 今後の拡張候補
- Amplify BQM 正式実装
- ブロック人数均等化の厳密QUBO化
- 部分修復（repair）アルゴリズム
- 重み自動チューニング

## 16. 失敗モード一覧（受け入れ条件の中核）
| 失敗モード | 現在の扱い |
|---|---|
| 設定ファイル欠落 | `ConfigError` を表示して安全停止 |
| 設定値型不一致 | `ConfigError` |
| 不正な時刻文字列 | `CSVFormatError` または `ConfigError` |
| duration がグリッドで割り切れない | `ConfigError` |
| 開始終了時刻矛盾 | `ConfigError`/`CSVFormatError` |
| 休憩長や転換長が 0 以下 | `ConfigError` |
| バンド数 0 | `CSVFormatError` |
| 出演可能CSVの列不足 | `CSVFormatError` |
| 存在しない/空 band_id | `CSVFormatError` |
| 出力先ディレクトリ作成失敗 | `OutputWriteError` |
| Amplify トークン未設定 | strict=false: フォールバック, strict=true: `SolverUnavailableError` |
| solver 結果が empty | `NoFeasibleSolutionError` |
| solver 結果ありだが妥当性 NG | `ValidationError` |

## 17. テスト実行
```bash
PYTHONPATH=src pytest -q
python -m compileall src
PYTHONPATH=src python -m timetable_amplify.main --config configs/default_config.json
PYTHONPATH=src python -m timetable_amplify.main --config configs/multiday_config.json
```
