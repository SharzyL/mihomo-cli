{
  description = "mihomoctl: TUI controller for mihomo";

  inputs = {
    nixpkgs.url = "nixpkgs";
    flake-parts.url = "flake-parts";
    treefmt-nix = {
      url = "github:numtide/treefmt-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = { flake-parts, ... }@inputs:
    let
      name = "mihomoctl";
      makePkg = { lib, buildPythonPackage, uv-build, httpx, msgspec, textual, pytestCheckHook, pytest-asyncio }:
        buildPythonPackage {
          pname = name;
          version = "0.1.0";
          pyproject = true;
          build-system = [ uv-build ];

          dependencies = [
            httpx
            msgspec
            textual
          ];

          nativeCheckInputs = [
            pytestCheckHook
            pytest-asyncio
          ];

          src = with lib.fileset; toSource {
            root = ./.;
            fileset = fileFilter
              (file: ! (lib.elem file.name [ "flake.nix" "flake.lock" ]))
              ./.;
          };
          meta.mainProgram = "mihomoctl";
        };

      shellOverride = pkgs: oldAttrs: {
        name = "${name}-dev-shell";
        src = null;
        nativeBuildInputs = (oldAttrs.nativeBuildInputs or [ ]) ++ (with pkgs; [
          uv
          basedpyright
          ruff
        ]);
      };
      overlay = final: _: {
        ${name} = final.python3Packages.callPackage makePkg { };
      };

    in
    # flake-parts boilerplate
    flake-parts.lib.mkFlake { inherit inputs; } {
      imports = [
        inputs.treefmt-nix.flakeModule
      ];

      flake.overlays.default = overlay;

      systems = inputs.nixpkgs.lib.systems.flakeExposed;

      perSystem = { system, config, pkgs, ... }: {
        packages.default = config.legacyPackages.${name};
        packages.${name} = config.packages.default;
        devShells.default = config.packages.default.overrideAttrs (shellOverride pkgs);
        legacyPackages = pkgs;

        _module.args.pkgs = import inputs.nixpkgs {
          inherit system;
          overlays = [ overlay ];
        };

        checks.basedpyright =
          let
            pkg = config.packages.default;
            env = pkgs.python3.withPackages (ps: pkg.dependencies ++ [ ps.pytest ps.pytest-asyncio ]);
          in
          pkgs.runCommand "${name}-basedpyright" { nativeBuildInputs = [ pkgs.basedpyright ]; } ''
            cp -r ${pkg.src} src && chmod -R +w src && cd src
            basedpyright --pythonpath ${env}/bin/python
            touch $out
          '';

        treefmt = {
          programs.ruff-format.enable = true;
          programs.ruff-check.enable = true;
          programs.nixpkgs-fmt.enable = true;
        };
      };
    };
}
