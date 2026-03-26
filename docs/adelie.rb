# Homebrew formula for Adelie
# To use: brew tap Ade1ie/tap && brew install adelie
#
# This file should be placed in a separate repo:
#   https://github.com/Ade1ie/homebrew-tap/Formula/adelie.rb
#
# After creating the repo, update the URL and sha256 for each release.

class Adelie < Formula
  desc "Autonomous AI Orchestration System — 10 agents, 6-phase lifecycle"
  homepage "https://github.com/Ade1ie/adelie"
  url "https://registry.npmjs.org/adelie-ai/-/adelie-ai-0.2.7.tgz"
  sha256 "db595e170087222d9dc1e3e9d4c269f0e6f1ac93"  # shasum from npm publish
  license "MIT"

  depends_on "node"
  depends_on "python@3.12"

  def install
    system "npm", "install", "--global", "--prefix", prefix, "adelie-ai@#{version}"
  end

  test do
    assert_match version.to_s, shell_output("#{bin}/adelie --version")
  end
end
