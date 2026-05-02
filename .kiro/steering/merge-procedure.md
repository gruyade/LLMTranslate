---
inclusion: manual
---

# main ブランチへのマージ手順

feature ブランチから main へマージする際の手順。
main への push で GitHub Actions の Build & Release ワークフローが自動実行され、
`.github/workflows/release.yml` の `body` がそのまま GitHub Release ページに表示される。

## 手順

### 1. CI 互換性の検証

main へのマージ前に、GitHub Actions 環境（test.yml / release.yml）で問題が起きないことを確認する。
ローカル環境（Windows）と CI 環境（ubuntu-latest / windows-latest）の差異が原因で失敗するケースが多い。

**原則: アプリ側のソースコード（`src/`）は変更しない。**
テスト・設定ファイル・ワークフロー側で対処する。
やむを得ず `src/` を変更する場合は、以下を満たす実装計画を立ててからユーザーに提示する:
- アプリとしての既存動作に悪影響がないこと
- 変更理由と影響範囲を明示すること

#### 1a. 依存関係の整合性チェック

テストで使用しているパッケージが `requirements.txt` と `pyproject.toml` の両方に記載されているか確認する。

```bash
# テストファイルの import 文から外部パッケージを抽出
grep -rh "^from\|^import" tests/ | sort -u

# requirements.txt の内容と照合
cat requirements.txt

# pyproject.toml の dev 依存と照合
cat pyproject.toml
```

チェック項目:
- テストで `import` しているサードパーティパッケージが `requirements.txt` に含まれているか
- `pyproject.toml` の `[project.optional-dependencies].dev` にも同じパッケージがあるか
- バージョン指定が両ファイルで一致しているか

**よくある見落とし**: ローカルに手動インストール済みのパッケージ（例: `hypothesis`）が設定ファイルに未記載。

#### 1b. クロスプラットフォーム互換性チェック

CI の test.yml は **ubuntu-latest**（Linux）で実行される。以下の差異に注意する。

| 項目 | ローカル (Windows) | CI (ubuntu-latest) |
|------|-------------------|-------------------|
| OS | Windows | Linux |
| Qt | ネイティブ | headless (`QT_QPA_PLATFORM=offscreen`) |
| 処理速度 | 通常 | 高速（非同期処理のタイミングが異なる） |
| パス区切り | `\` | `/` |
| Win32 API | 利用可能 | 利用不可 |

**タイミング依存テストの確認**:
- `time.sleep()` や `_process_events_until()` で待機するテストは、CI の高速環境で競合状態が発生しやすい
- シグナルの接続は、トリガーとなる操作の**前**に行うこと
- 非同期処理が想定より早く完了するケースを考慮し、early return パスを設けること

**プラットフォーム固有コードの確認**:
- `ctypes.windll` 等の Windows 専用 API を使うコードがテストで実行されないか
- テスト対象が Windows 専用機能の場合は `pytest.mark.skipif` でスキップ条件を付与

#### 1c. ワークフロー設定の確認

```bash
# test.yml: テスト実行環境の確認
cat .github/workflows/test.yml

# release.yml: ビルド環境の確認
cat .github/workflows/release.yml
```

チェック項目:
- test.yml の `pip install` コマンドが `requirements.txt` を参照しているか
- release.yml の Python バージョンが test.yml のマトリクスに含まれているか
- `build.spec` の `hiddenimports` に新規追加した翻訳モジュール等が含まれているか

### 2. 仕様の書き出しとコード整理

feature ブランチでの繰り返し修正で実装がパッチワーク的になっていないかを確認し、整理する。

#### 2a. 確定仕様の書き出し

feature ブランチで変更した各モジュールについて、現在の動作仕様を箇条書きで書き出す。
コードから読み取れる「実際の動作」を記述し、途中で破棄された設計や残骸を洗い出す。

確認観点:
- 定数の名前・コメントが現在の用途と一致しているか
- 未使用の変数・引数・メソッドが残っていないか
- 同じデータ構造やロジックが複数箇所で重複定義されていないか
- 条件分岐が現在の仕様で到達不能になっていないか
- docstring が現在の動作を正しく説明しているか

#### 2b. 実装の整理

書き出した仕様に基づいて、以下を整理する:

- 冗長な状態管理の統合（例: 全要素一括制御なのに個別状態を持っている）
- 不要になったヘルパーメソッドの削除
- 定数コメントの実態への修正
- 重複コードのヘルパー抽出

**原則: 動作を変えない。** リファクタリングのみ行い、機能変更は含めない。

#### 2c. テストの整理

実装中のテスト修正は動作確認に必要な最小限にとどめ、このステップで最終的に整理する。

- テストが整理後の実装構造（内部API）を正しく参照しているか確認
- 実装中に追加した暫定的なテスト修正を、確定仕様に基づいて書き直す
- テストのゾーン定義・境界値が実装のロジックと一致しているか確認
- 不要になったインポートやヘルパーを削除

### 3. ローカルテスト通過を確認

```bash
pytest -v
```

全テスト通過を確認してから次へ進む。

### 4. 変更ログの収集

前回の main マージ以降のコミットログを取得する。

```bash
# main との差分コミット一覧
git log main..HEAD --oneline --no-merges

# ファイル変更統計
git diff main --stat | Select-Object -Last 1
```

### 5. release.yml の body を書き換え

`.github/workflows/release.yml` の `body` セクションを、収集した変更ログで更新する。

書き換え対象箇所:
```yaml
      - name: Create GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          body: |
            ## LLMTranslate Auto Build
            ...  ← ここを書き換える
```

body のフォーマット:
```markdown
## LLMTranslate Auto Build

**Commit:** ${{ github.sha }}
**Branch:** ${{ github.ref_name }}

### 変更内容
- feat: 〇〇機能を追加
- fix: △△のバグを修正

### インストール方法
1. `LLMTranslate.zip` をダウンロードして展開
2. `LLMTranslate.exe` を実行
```

- コミットの type プレフィックス（feat, fix, refactor 等）でグループ化
- 各項目は 1 行で簡潔に
- 破壊的変更がある場合は `⚠ BREAKING:` プレフィックスを付与
- 「インストール方法」セクションは常に末尾に残す

### 6. body 書き換えをコミット

```bash
git add .github/workflows/release.yml
git commit -m "docs: リリースノート更新"
```

### 7. main にマージ

```bash
git checkout main
git merge --no-ff <feature-branch> -m "merge: <変更サマリ1行>"
```

`--no-ff` でマージコミットを必ず作成し、履歴を明確にする。
push はユーザーが手動で行う（`git push origin main` で Build & Release が自動実行される）。
