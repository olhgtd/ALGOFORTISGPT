from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def read(path:str)->str:
    return (ROOT/path).read_text(encoding="utf-8")

def test_split_package_names_and_launchers():
    build=read("build/tools/build_owner_user_installers.ps1")
    for marker in ("AlgoFortis-Owner-Setup","AlgoFortis-User-Setup","AlgoFortisOwner.exe","AlgoFortisUser.exe"):
        assert marker in build

def test_role_launcher_has_distinct_mutexes_and_role_url():
    src=read("build/tools/AlgoFortisLauncher.cs")
    for marker in ("OWNER_APP","USER_APP","AlgoFortis_Owner_App_Instance_Mutex","AlgoFortis_User_App_Instance_Mutex","?app="):
        assert marker in src
    assert "--mode LOCAL_PRIVATE" in src

def test_role_installer_excludes_generic_launcher():
    src=read("build/tools/algofortis_role_installer.iss")
    assert 'Excludes: "AlgoFortis.exe"' in src
    assert "{#MyAppExeName}" in src

def test_approved_fortress_master_is_build_authority():
    src=read("build/tools/build_owner_user_installers.ps1")
    stage=read("build/tools/stage_role_app.ps1")
    assert "assets\\branding\\AlgoFortis\\AlgoFortis_Logo_Master.png" in src
    assert "generate_brand_assets.ps1" in stage
    assert "ROLE_STAGE_BRAND=FORTRESS_MASTER" in stage

def test_frontend_role_is_locked_by_desktop_app():
    main=read("dashboard/web/src/main.tsx")
    dash=read("dashboard/web/src/DashboardV3App.tsx")
    assert 'get("app")' in main
    assert 'app === "owner" || app === "user"' in main
    assert "lockedWorkspace" in main
    assert "lockedWorkspace" in dash

def test_real_install_certification_covers_both_roles_and_data_preservation():
    cert=read("build/tools/certify_owner_user_installers.py")
    assert "AlgoFortis-Owner-Setup.exe" in cert
    assert "AlgoFortis-User-Setup.exe" in cert
    assert "LOCALAPPDATA" in cert
    assert "LOCAL_PRIVATE" in cert
    assert "READ_ONLY/DISARMED" in cert
