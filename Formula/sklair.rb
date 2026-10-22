class Sklair < Formula
  desc "HTML compiler for components, Lua, and document generation"
  homepage "https://sklair.numelon.com"
  version "0.4.0"
  license "AGPL-3.0-only"

  on_macos do
    on_arm do
      url "https://github.com/numelon-oss/sklair/releases/download/v0.4.0/sklair-darwin-arm64.tar.gz"
      sha256 "bdedf5c340fbf3151c24a2ed5242ff27c55b02566069345f8de86c0127ca566a"
    end
    on_intel do
      url "https://github.com/numelon-oss/sklair/releases/download/v0.4.0/sklair-darwin-amd64.tar.gz"
      sha256 "d038bd29d7b7524ec3667669a1d7c7080f0b51cf258ce742e740024a2a841491"
    end
  end

  on_linux do
    on_arm do
      url "https://github.com/numelon-oss/sklair/releases/download/v0.4.0/sklair-linux-arm64.tar.gz"
      sha256 "0936581b5a9f1223cf1df0c1d03b79b97d1ce2e8e585c815adc5b3d7f15436d9"
    end
    on_intel do
      url "https://github.com/numelon-oss/sklair/releases/download/v0.4.0/sklair-linux-amd64.tar.gz"
      sha256 "1c5a20fac61cd1c69735ab3cd5e11434f59c9b78de04323d2befbb88c6014826"
    end
  end

  def install
    bin.install "sklair"
  end
end
