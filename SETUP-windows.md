# となりを Windows で使えるようにする（その PC の Claude Code が読む手順書）

このフォルダは、macOS で作って毎日使っている学びのアプリ「となり」です。声で質問し、答えを待つあいだに別の話題へ移り、文字と図で返ってくる答えを順に読みます。この文書は、Windows の PC で同じアプリを使えるようにするために、その PC の Claude Code が読む手順書です。README の「Claude Code に貼る文」を貼られた Claude Code は、ここから始めます。

## 先に知っておくこと

本人がすることは、最後にアプリを開いて話すことだけ、にするのが目標です。入れるもの・入れる場所・かかる時間は、入れる前に本人に見せて確かめます。設計の判断（`DESIGN-となり-声で回す概念の学び-2026-10.md`）は変えません。直すのは、この PC で動かないところだけです。直したら `uv run --group dev pytest` を流し、Mac 向けの動きを変えていないことを確かめます（OS の違いは `sys.platform` などの分岐で書く）。

Windows 向けにすでに入っているものは次のとおりです。

| 場所 | 中身 |
|---|---|
| `setup.ps1` | uv・ffmpeg・speech.cpp を入れ（入っていれば飛ばす）、`uv sync` と `prepare.py` を流す |
| `prepare.py` | speech・ffmpeg の場所を記録の置き場の `.env` に書く、Haas のモデルを取る、先生役のモデルを claude で1回確かめる（opus が使えなければ sonnet にする）、準備の表を出す、スタートメニューとデスクトップにショートカットを作る |
| `launch.py` | サーバーを裏で立て、Edge のアプリ窓で開く。窓を閉じると15秒後にサーバーも止まる。ショートカットは `.venv\Scripts\pythonw.exe launch.py`（黒い窓が出ない） |
| `server/` | 記録の置き場は `%LOCALAPPDATA%\tonari`。Apple の聞き取りが無い PC では Haas だけで聞く。`claude.exe` を先に探す。`/api/health` が準備の確かめを返す |
| 画面 | 話題を移るキーは Alt（Alt+N・Alt+]・Alt+1〜9）。「設定を開く」で、キーの割り当て・聞き取りの方式・ElevenLabs の鍵・先生役のモデル・この PC の準備を見て変えられる |

`setup.ps1`・ショートカット・Edge の窓・マイクは、作者の Mac では確かめられていません。この PC で初めて動かすので、止まったら表示を読んで直します。

## 手順

1. 本人に、これから入れるものを見せて確かめる。uv（Python の実行・astral.sh の公式の入れ方）、ffmpeg（録音の変換・`winget install --id Gyan.FFmpeg -e`。winget の同意を自動で受ける）、speech.cpp（端末内の聞き取り Haas を動かす道具・`%LOCALAPPDATA%\Programs\speech.cpp` に入る・GPU のドライバの Vulkan が要る）、Haas-ja-v1.0 のモデル（初回だけダウンロード）、Python の部品（`.venv` に入る）。
2. このフォルダの PowerShell で `powershell -ExecutionPolicy Bypass -File .\setup.ps1` を流す。最後に準備の表が出て、「用意ができました」なら次へ。「要対応」があれば、表の直し方に沿って直し、もう一度流す。
3. `uv run --group dev pytest` を流し、全部通ることを確かめる。
4. 本人に、スタートメニューかデスクトップの「となり」を開いてもらう。窓が開いたら、マイクの許可を1回だけ求められるので許可してもらう。
5. 本人に、Alt+N で話題を作って一言話し、もう一度 Space で送ってもらう。答えが返ることを確かめる。
6. 窓を閉じ、20秒ほどたってから開き直し、同じ話題で「さっきの続きで」と聞いてもらう。前のやりとりを覚えていることを確かめる。

## 完成と言ってよい条件

次が全部通ったら完成とし、結果を数字と表示で本人に短く報告します。`pytest` が全部通る。`setup.ps1` の最後の表が「用意ができました」になる。ショートカットから開いた窓で、声の往復が1回できる（秒数を書く）。窓を閉じて開き直すと続きを覚えている。窓を閉じたあと、`python`・`pythonw`・`claude.exe` が残っていない（タスクマネージャーか `Get-Process` で見る）。

## つまずきそうな所

文字コード。Windows の既定は cp932 です。ファイルとパイプは utf-8 を指定します（`launch.py` は子に `PYTHONUTF8=1` を渡している）。読み書きで文字化けやエラーが出たら、その箇所に `encoding="utf-8"` を足します。

先生役が起動しない。サーバーを `--reload` や `--workers` 付きで起動すると、子プロセスを立てられないイベントループに変わります。`launch.py` は付けていません。手で確かめるなら、`claude -p --safe-mode --restricted --tools Read,Grep,Glob --model opus --input-format stream-json --output-format stream-json --include-partial-messages --verbose` に stream-json の1行を流して、答えが返るかを見ます。claude を API キーなどの環境変数で動かしている PC は、記録の置き場の `.env` に `TONARI_KEEP_ANTHROPIC_ENV=1` を書きます。

聞き取り。Vulkan（`C:\Windows\System32\vulkan-1.dll`）が無い PC には speech.cpp が入りません。GPU のドライバを入れ直すか、画面の「設定を開く」で ElevenLabs の鍵を入れて Scribe を使います（そのときは録音が ElevenLabs に送られる）。Mac で測った値は次のとおりで、Windows では Apple が無いので Haas の行が1本目です。

| 方式 | 文字誤り率（合成音声6本・用語の一覧つき） |
|---|---|
| Apple だけ | 14.2% |
| Haas だけ（用語なし） | 13.8% |
| Haas だけ（用語つき） | 6.0% |
| Scribe ＋用語の一覧 | 0.0% |

入れたばかりのときは用語集が空なので、専門の用語は聞き違えやすいです。話題を重ねて概念が溜まると、整形役が直しやすくなります。測り直すなら、`tests/audio/texts.txt` の3行を本人に読み上げてもらい、`名前-1.wav`〜`名前-3.wav` で `tests/audio` に置いて `uv run python -m tests.stt_eval --haas` を流します（試しの音声は macOS の声で作るので配っていない）。

窓。Edge が見つからなければ Chrome、どちらも無ければふだんのブラウザのタブで開きます（タブを閉じても、15秒後にサーバーが止まる）。窓の置き場（マイクの許可を覚えている所）は記録の置き場の `browser` です。

## してはいけないこと

アプリの中から Claude の API を直接呼ばない（必ず `claude -p` を通す）。鍵・録音・学びの記録（DB）をフォルダに入れない。DESIGN の設計の判断を、移植のついでに変えない（変えたくなったら、理由をつけて README に提案として書く）。Mac 向けの動きを変えない。

## 終わったら

この PC で直したところと、つまずいた所を `CLAUDE.md` の末尾に足し、区切りごとに commit します。作者に戻すときは、GitHub で fork して pull request を出します。
