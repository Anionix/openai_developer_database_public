{
  description = "Public companion for the unofficial OpenAI Developers database package";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
  };

  outputs =
    { nixpkgs, ... }:
    let
      systems = [
        "aarch64-darwin"
        "x86_64-darwin"
        "aarch64-linux"
        "x86_64-linux"
      ];
      forAllSystems =
        f:
        nixpkgs.lib.genAttrs systems (
          system:
          f (
            import nixpkgs {
              inherit system;
            }
          )
        );
      publicRuntime =
        pkgs:
        let
          python = pkgs.python312.withPackages (ps: [
            ps.numpy
          ]);
        in
        [
          pkgs.bash
          pkgs.coreutils
          pkgs.duckdb
          python
          pkgs.ripgrep
          pkgs.sqlite
        ];
    in
    {
      devShells = forAllSystems (
        pkgs:
        {
          default = pkgs.mkShell {
            packages = publicRuntime pkgs;

            shellHook = ''
              echo "OpenAI Developers database public companion shell"
              echo "Validate public repo: nix run path:\$PWD#validate-public"
            '';
          };
        }
      );

      apps = forAllSystems (
        pkgs:
        let
          validatePublic = pkgs.writeShellScriptBin "validate-public" ''
            set -euo pipefail
            export PATH="${pkgs.lib.makeBinPath (publicRuntime pkgs)}:$PATH"
            exec ${pkgs.bash}/bin/bash scripts/validate_public.sh
          '';
        in
        {
          validate-public = {
            type = "app";
            program = "${validatePublic}/bin/validate-public";
            meta.description = "Validate that the public companion repository contains no excluded data artifacts.";
          };
        }
      );

      checks = forAllSystems (
        pkgs:
        {
          validate-public = pkgs.runCommand "openai-developers-public-validate"
            {
              nativeBuildInputs = publicRuntime pkgs;
            }
            ''
              cp -R ${./.} source
              chmod -R u+w source
              cd source
              bash scripts/validate_public.sh
              touch $out
            '';
        }
      );
    };
}
