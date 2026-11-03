# となり（声で回す学び）

自分の PC だけで使う学びのアプリです。話題を何本も並べ、話題Aで声で質問したら答えを待たずに話題Bへ移り、答えが届いた話題に戻って読みます。答えは文字と図で返り、説明の中心の概念を、上に上位概念、下に下位概念、左右に対の概念、斜めに関係する概念を置いた図で見せます。理解度は概念ごとの申告と、関係ごとの確かめで持ちます。答えを開く前に予想を一言話す帯と、時間をおいて戻ったときに出る確かめの問いがあります（v0.3）。設計は `DESIGN-となり-声で回す概念の学び-2026-10.md`、調べた材料は `research/` にあります。文書の中の「本人」は、このアプリを使う人のことです。

Mac で作って毎日使っています。Windows では、下の「Windows で使う」の文を Claude Code に貼ると、clone から起動までを Claude Code が進めます。

## 要るもの

Claude Code（`claude` コマンド）が入っていて、ログインして動くこと。先生役（答えを書く役）と整形役（文字起こしを直す役）は、`claude -p` をあなたのログインのまま子プロセスで動かします。Claude の API キーは使わず、使った分はあなたの Claude のプランの枠から減ります。先生役の既定は opus で、使えないプランなら `TONARI_TUTOR_MODEL=sonnet` で変えます。

ほかに `uv`（Python の実行）と `ffmpeg`（録音の変換）が要ります。声を文字にするのは、Mac では Apple の聞き取り（端末内・無料）、Apple の無い PC では speech.cpp で動かす Haas-ja-v1.0（端末内・無料・日本語向け）です。ElevenLabs の鍵を入れると Scribe も使えます（そのときは録音が ElevenLabs に送られます）。

## Mac で使う

Xcode のコマンドラインツール（swiftc）も要ります。`bash app/build_app.sh` でアプリ「となり」（`~/Applications/となり.app`）を作り、開きます。Spotlight で「となり」と打つか、Finder でホームの中の「アプリケーション」を開きます（サイドバーの「アプリケーション」は Mac 全体の /Applications なので、そこには無い）。アプリはサーバーを自分で起動し、閉じるとサーバーも止めます（`run.sh` で先に起動していればそれを使い、閉じても止めない）。最初に話すとき、macOS がマイクの使用を1回だけ確かめます。

アプリはビルドした時点の uv・claude・ffmpeg の場所を覚えているので、入れ直して場所が変わったら作り直します。作り直したら、開いているアプリを一度終了して開き直します。アプリを使わずにブラウザで開くなら `./run.sh`（Chrome で `http://127.0.0.1:4880/`）。窓を出さずに起動から停止までを確かめるのは `~/Applications/となり.app/Contents/MacOS/Tonari --selftest --port 4882 --snapshot /tmp/t.png`（`--js '<式>'` で画面を操作してから撮れる）。サーバーのログは `~/Library/Logs/tonari/server.log`。

## Windows で使う

Claude Code を入れてログインしたあと、好きなフォルダで PowerShell を開いて `claude` を打ち、次の文を貼って送ります。Claude Code が clone から、入れるものの確認、`setup.ps1`、試験、起動までを進めます。

Claude Code に貼る文:

```text
声で学ぶアプリ「となり」をこの PC で使えるようにしてください。
1. https://github.com/nomura-t/tonari を、ホームの下の tonari フォルダ（%USERPROFILE%\tonari）に git clone してください。
2. そのフォルダの SETUP-windows.md を読み、その手順どおりに進めてください。何かを入れる前に、入れるもの・入れる場所・かかりそうな時間を私に見せて、確かめてから入れてください。
3. 最後に、私がふだんどう起動すればよいかと、確かめた結果を短く教えてください。つまずいて直したことがあれば、そのフォルダの CLAUDE.md の末尾に書いておいてください。
```

手でやるなら、`git clone https://github.com/nomura-t/tonari.git` のあと、そのフォルダの PowerShell で `powershell -ExecutionPolicy Bypass -File .\setup.ps1` を流します。入るのは uv・ffmpeg・speech.cpp と Python の部品で、最後に準備の表が出て、スタートメニューとデスクトップに「となり」ができます。開くと Edge のアプリ窓になり、窓を閉じると15秒後に裏のサーバーも止まります。中身は `SETUP-windows.md`、起動役は `launch.py`、用意の仕上げは `prepare.py` です。

## 設定の画面

左の列の下の「設定を開く」で開きます。この PC の準備（Claude Code・ffmpeg・聞き取りの道具・Scribe の鍵が使えるか、使えないときの直し方）、キーの割り当て、聞き取りの方式、ElevenLabs の鍵、先生役のモデル（opus か sonnet。新しい話題から使う）、読み方（送ったら移る・読む前の予想）を、ここで見て変えます。キーは「変える」を押してから使いたいキーを押すと変わり、変えていない操作は OS の既定（Mac は ⌘、ほかは Alt）のままです。同じキーを2つの操作に割り当てようとすると断ります。準備が足りないときは、左の列と最初の画面に1行で知らせます。

## 操作

| キー | すること |
|---|---|
| ⌘N（Windows は Alt+N） | 新しい話題を作り、そのまま録音を始める |
| Space | 録音を始める・もう一度押すと送る（文字の欄にいるときは効かない）。予想の帯が出ているときは予想を、確かめの帯が出ているときは答えを話す |
| Esc | 録音をやめる（送らない） |
| ⌘]（Windows は Alt+]） | 答えの届いた話題へ移る（古い順）。届いていなければ待っている話題へ |
| ⌘1〜⌘9（Windows は Alt+1〜9） | 左の列の順で話題を開く |
| Enter（文字の欄） | 打った文を送る |
| Enter（予想の帯が出ているとき） | 予想せずに答えを開く |

表のキーは既定の割り当てで、設定の画面で変えられる。送ったあと答えの届いた話題へ自動で移るかは、設定の画面の「送ったら答えの届いた話題へ移る」で切り替える。聞き取りの方式も同じ画面で、「精度優先（毎回 Scribe）」「自動（口座の残りが 5,000 を切ったら Apple だけ）」「端末だけ（Apple）」から選ぶ。

答えが届いた話題を開くと、答えは畳まれて「読む前に、答えはどうなると思いますか」と出る。Space で一言予想して送ると答えが開き、予想が答えの上に残る（設定の画面の「答えを読む前に予想を一言話す」で止められる）。確かめの問いは答えの下には出ず、答えを開いてから2分以上たってその話題に戻ったときに、答えを畳んで1つだけ上の帯に出る。声で答えると先生役が判定し、二度目の判定役と一致した当たり・半分だけが理解の記録に入る。「確認ですけど〜ですよね」と自分の言葉で言い直したときも判定する（DESIGN 13章）。

答えの図は中身に合わせて先生役が選ぶ（分岐の木・時間軸・流れ・比較の表・重なりの図・計算の例・たとえ・階層の木・関係の図・位置の図、一言で足りるなら文だけ）。図の上に表現の名前と、その形にした理由が出る。答えの下の「短く」「別の見せ方で」「詳しく」で同じ中身を言い直してもらえる（「別の見せ方で」は前の図と新しい図を横に並べる）。上の帯の「自動・短く・詳しく」は話題ごとの答えの長さで、自動は確かめの問いに答えられた概念ほど短くする。

本人の発言の下線は整形役が直した箇所で、押すと聞き取りどおりの字に戻した文で聞き直す画面になる。点線は決めきれなかった箇所（候補は字に重ねると出る）。「直して聞き直す」で書き換えた字は聞き違いの台帳に入り、次から聞き取りの手がかりになる。

図の札を押すと右の地図がその概念を中心に描き直し、2回押すとその概念の説明を頼む。右の地図では、概念の申告（分かる・あやしい・分からない）と、関係ごとの確かめ（✓・?）を付けられる。

## 記録の置き場

Mac は `~/Library/Application Support/tonari/`、Windows は `%LOCALAPPDATA%\tonari\`（SQLite の `tonari.db`、本人の録音 `audio/`、棚の本文の写し `corpus/`、整形役の作業場所 `work/`）。リポジトリには入れない。先生役の会話は Claude Code の記録（`~/.claude/projects/` の下、作業フォルダ `corpus/` の分）に残り、`--resume` で続きから始まる。

## 守っていること

Claude の API キーは使わない。先生役（opus）と整形役（sonnet）は、手を加えていない `claude -p` を本人のログインのまま子プロセスで動かし、子の環境から `ANTHROPIC_*` を外す。先生役は `--restricted --tools Read,Grep,Glob` で棚の写しだけを読む（棚は作者の手元の道具で、無ければ資料なしで答える）。サーバーは 127.0.0.1 だけで待ち受け、`/api` は独自の見出し `X-Tonari: 1` が無いと断る。Scribe を使うときは録音が ElevenLabs に送られる。

## 設定（環境変数）

環境変数のほか、記録の置き場の `.env` に `TONARI_…=値` の行で書いてもよい（環境変数があればそちらが勝つ。`prepare.py` はここに書く）。

| 変数 | 既定 | 中身 |
|---|---|---|
| `TONARI_DATA_DIR` | Mac `~/Library/Application Support/tonari`・Windows `%LOCALAPPDATA%\tonari` | 記録の置き場（試験のときは別の場所にする） |
| `TONARI_PORT` | 4880 | 待ち受けの番号 |
| `TONARI_TUTOR_MODEL` / `_EFFORT` | opus / （既定） | 先生役 |
| `TONARI_TUTOR_MAX_ALIVE` / `_IDLE_SEC` | 6 / 1800 | 常駐させる先生役の上限と、閉じるまでの秒数 |
| `TONARI_FIXER_MODEL` / `_EFFORT` | sonnet / low | 整形役 |
| `TONARI_SCRIBE` | auto | Scribe の既定（画面で変えた値が優先） |
| `TONARI_ELEVEN_MIN_REMAINING` | 5000 | 自動のとき、口座の残りがこれを切ったら Scribe を使わない |
| `TONARI_RETURN_AFTER_SEC` | 120 | 答えを開いてからこれだけたって話題に戻ったら、その答えの確かめの問いを1つ出す（DESIGN 13.2） |
| `TONARI_LOCAL_ASR` | auto | Scribe を使わない回に speech.cpp の Haas-ja-v1.0 を使うか。auto は Apple の無い PC でだけ使い、`haas` は Mac でも Apple と並べて2本目にし、`off` は使わない（測った結果は DESIGN 3.1.1） |
| `TONARI_SPEECH_BIN` | （空） | speech.cpp の `speech` の場所。空なら PATH と `~/.local/bin/speech`（.exe も）と Windows の `%LOCALAPPDATA%\Programs\speech.cpp\current\speech.exe` を探す |
| `TONARI_FFMPEG_DIR` | （空） | ffmpeg と ffprobe のあるフォルダ。空なら PATH と Windows の winget の置き場を探す |
| `TONARI_EXIT_WHEN_CLOSED` | （空） | `1` で、画面が閉じられて15秒たったらサーバーが止まる（`launch.py` が立てる） |
| `TONARI_STT_BIN` | `stt/bin/stt-helper` | Apple の聞き取りの道具（Mac だけ） |
| `ELEVENLABS_API_KEY` | （空） | Scribe の鍵。環境変数に無ければ、記録の置き場の `.env` の `ELEVENLABS_API_KEY=` の行を読む |
| `TONARI_CLAUDE` | （空） | `claude` の場所。空なら PATH を探す（Windows は `claude.exe` を先に） |
| `TONARI_KEEP_ANTHROPIC_ENV` | （空） | `1` にすると子の環境から `ANTHROPIC_*` を外さない（claude を API キーなどで動かしている PC 向け） |
| `TONARI_SHELF_LIB` | `.claude/.artifacts` | 棚の写しの場所（作者の手元の道具。無ければ資料なしで動く） |

## 検査

規則の検査は `uv run --group dev pytest`（直しすぎ・判定の根拠・札の読み取り・対の向き・聞き違いの拾い方・「」の照合・図の塊ごとの決まり）。文字起こしの方式ごとの誤り率は `uv run python -m tests.stt_eval`（Apple だけ）、`--scribe`（Scribe の用語あり・なし）、`--fixer`（Apple＋整形役）、`--haas`（Haas の用語あり・なし）、`--fixer --haas [--no-glossary]`（Apple と Haas の2本を整形役に）。整形役は回ごとに揺れるので、比べるときは3回以上回す。試しの音声は `tests/audio/`（正解の文と用語の一覧）。合成音声6本は macOS の声の使用許諾で再配布できないのでリポジトリに入れておらず、Mac では `bash tests/audio/make_mac.sh` で作る。ほかの PC では `texts.txt` を読み上げて録った wav を「名前-行の番号.wav」で置く。`spike/` は 2026-10-29 に方式を決めたときの試し（opus 3本の同時起動、Apple の2方式の文脈の語と別候補）。

## 使ってよい範囲

MIT ライセンスです（`LICENSE`）。声の聞き取りに使う speech.cpp（MIT）と Haas-ja-v1.0（Apache-2.0）は、それぞれの配布元から入れます。
