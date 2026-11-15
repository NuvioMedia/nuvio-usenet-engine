# Nuvio Usenet Engine

Cross-platform Usenet streaming engine for Nuvio (under active development).

The engine turns an NZB and NNTP provider configuration into seekable HTTP media
streams. It includes pipelined NNTP connections, SIMD yEnc decoding, lazy archive
handling, file and episode selection, subtitles, and bounded in-memory article
caching. Android binaries are distributed as versioned GitHub Release assets.

This is a standalone sidecar process. The NuvioTV application supplies its
settings, indexer searches, UI and player integration separately. See
[NUVIO-INTEGRATION.md](NUVIO-INTEGRATION.md) for playback behavior and Android
integration details, and [NOTICE.md](NOTICE.md) for provenance and dependencies.

## Build and test

Run commands from this repository's root. Host builds require Go 1.27+ and a
working CGO C/C++ compiler. The vendored RapidYenc wrapper includes upstream
archives for supported Linux, macOS and Windows hosts.

```sh
go build -trimpath -o build/nuvio-usenet ./cmd/nuvio-usenet
python3 -m unittest discover -s tests -p 'usenet_prebuilts_test.py'
go test -race ./... github.com/javi11/nntppool/v4 -timeout 10m
go test github.com/javi11/sevenzip/... -timeout 5m
go test -race github.com/javi11/sevenzip/... \
  -run 'TestMetadataAllocationsAreBounded|TestReaderCancellation|TestKeyDerivation|FuzzReaderMetadata' \
  -timeout 2m
```

The executable expects a JSON bootstrap record on stdin; it is not an
interactive command-line downloader. The bootstrap supplies a control token,
optional CA certificates, a memory target and an optional NZB cache directory.
The process reports `{"protocol":1,"port":...}` on stdout and binds to
`127.0.0.1`. Keep stdin open: EOF shuts the process down.

Control requests use bearer authentication. `POST /sessions` opens an NZB,
`DELETE /sessions/<id>` releases it, and `GET /sessions/<id>/diagnostics` reports
diagnostics. Players read the returned capability URLs over ordinary HTTP,
including byte-range requests. See [main.go](cmd/nuvio-usenet/main.go) and
[server.go](internal/engine/server.go) for the bootstrap and session schemas.

## Android release assets

```sh
python3 scripts/fetch_prebuilts.py
python3 scripts/check_prebuilts.py
```

`prebuilt/manifest.json` pins an exact release, source digest, binary checksums
and build toolchain. Downloads are verified before installation and cached in
`prebuilt/`. Generated Android binaries are ignored by Git.

To rebuild all four ABIs, install the pinned Go toolchain, Android NDK
`29.0.14206865` and CMake `3.22.1`, then run:

```sh
python3 scripts/build_android.py \
  --ndk "$ANDROID_HOME/ndk/29.0.14206865" \
  --cmake "$ANDROID_HOME/cmake/3.22.1/bin/cmake" \
  --release-repository haaihond/nuvio-usenet-engine
python3 scripts/check_prebuilts.py
```

Commit and push the source and regenerated manifest. The **Publish Usenet native
assets** workflow on `main` rebuilds with the pinned toolchain, requires matching
checksums, and publishes immutable source-hash release assets. It can also be
started manually. Tests that fetch a new release may need rerunning after its
first publication.

Alternatively, publish the verified local outputs from a clean, pushed checkout
with GitHub CLI release access:

```sh
python3 scripts/publish_prebuilts.py --target "$(git rev-parse HEAD)"
```

Each release contains `libnuvio_usenet-<abi>.so` for `arm64-v8a`, `armeabi-v7a`,
`x86` and `x86_64`, plus its manifest. These are Android PIE executables targeting
API 24 with 16 KiB page alignment. Their `.so` names allow Android to install them
in the executable native library directory; they are launched, not loaded via
JNI.

## Using the engine in NuvioTV

Pin this repository at `native/usenet` in NuvioTV, for example as a Git submodule.
Initialize submodules in developer and CI checkouts. The included
`android.gradle.kts` is a NuvioTV adapter that expects that location; the normal
build downloads verified release assets, while `-PbuildUsenetFromSource=true`
builds locally. Package `licenses/` as app assets and retain the executable
filename `libnuvio_usenet.so`.

This extraction does not change NuvioTV's dependency automatically. Its launcher
and the engine continue to use protocol version 1. When transferring the engine
repository to an organization, update the Go module/import paths and release
repository together, regenerate the manifest and publish matching assets.

## History and license

Extracted from the cleaned `full-nntp` branch of
[haaihond/NuvioTV](https://github.com/haaihond/NuvioTV) at
`f222d044f69967764804236a65c6ec7d877b377d`, with engine development history and
original authors preserved. Historical commits predate the standalone module
and CI layout; the extraction changes commit hashes and removes signatures.

The project license is [GNU GPLv3](LICENSE). Third-party code retains its
respective licenses; preserve [NOTICE.md](NOTICE.md), [licenses/](licenses/) and
the notices in [third_party/](third_party/).
