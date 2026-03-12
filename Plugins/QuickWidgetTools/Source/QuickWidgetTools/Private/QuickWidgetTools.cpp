#include "QuickWidgetTools.h"

#include "AssetRegistry/AssetRegistryModule.h"
#include "EditorUtilitySubsystem.h"
#include "EditorUtilityWidgetBlueprint.h"
#include "ToolMenus.h"
#include "ToolMenuEntry.h"

#include "Interfaces/IPluginManager.h"
#include "Misc/Paths.h"
#include "Modules/ModuleManager.h"
#include "IPythonScriptPlugin.h"

#define LOCTEXT_NAMESPACE "FQuickWidgetToolsModule"

void FQuickWidgetToolsModule::StartupModule()
{
    RegisterPluginPythonPath();

    UToolMenus::RegisterStartupCallback(
        FSimpleMulticastDelegate::FDelegate::CreateRaw(this, &FQuickWidgetToolsModule::RegisterMenus)
    );
}

void FQuickWidgetToolsModule::ShutdownModule()
{
    if (UToolMenus::IsToolMenuUIEnabled())
    {
        UToolMenus::UnRegisterStartupCallback(this);
        UToolMenus::UnregisterOwner(this);
    }
}

FString FQuickWidgetToolsModule::GetPluginPythonPath() const
{
    static const FString PluginName = TEXT("QuickWidgetTools");

    TSharedPtr<IPlugin> Plugin = IPluginManager::Get().FindPlugin(PluginName);
    if (!Plugin.IsValid())
    {
        UE_LOG(LogTemp, Error, TEXT("QuickWidgetTools: Could not find plugin '%s'"), *PluginName);
        return FString();
    }

    FString PythonPath = FPaths::Combine(Plugin->GetBaseDir(), TEXT("Content"), TEXT("Python"));
    PythonPath = FPaths::ConvertRelativePathToFull(PythonPath);
    FPaths::NormalizeDirectoryName(PythonPath);

    return PythonPath;
}

void FQuickWidgetToolsModule::RegisterPluginPythonPath()
{
    const FString PythonPath = GetPluginPythonPath();
    if (PythonPath.IsEmpty())
    {
        return;
    }

    if (!FPaths::DirectoryExists(PythonPath))
    {
        UE_LOG(LogTemp, Warning, TEXT("QuickWidgetTools: Python folder does not exist: %s"), *PythonPath);
        return;
    }

    IPythonScriptPlugin* PythonScriptPlugin =
        FModuleManager::LoadModulePtr<IPythonScriptPlugin>("PythonScriptPlugin");

    if (!PythonScriptPlugin)
    {
        UE_LOG(LogTemp, Warning, TEXT("QuickWidgetTools: PythonScriptPlugin is not loaded/enabled"));
        return;
    }

    FString PythonPathForScript = PythonPath;
    PythonPathForScript.ReplaceInline(TEXT("\\"), TEXT("/"));

    const FString PythonCommand = FString::Printf(
        TEXT("import sys\n")
        TEXT("plugin_path = r'%s'\n")
        TEXT("if plugin_path not in sys.path:\n")
        TEXT("    sys.path.append(plugin_path)\n")
        TEXT("print(f'[QuickWidgetTools] Added python path: {plugin_path}')\n")
        TEXT("else:\n")
        TEXT("    print(f'[QuickWidgetTools] Python path already present: {plugin_path}')\n"),
        *PythonPathForScript
    );

    const bool bExecuted = PythonScriptPlugin->ExecPythonCommand(*PythonCommand);

    if (bExecuted)
    {
        UE_LOG(LogTemp, Log, TEXT("QuickWidgetTools: Registered plugin Python path: %s"), *PythonPath);
    }
    else
    {
        UE_LOG(LogTemp, Error, TEXT("QuickWidgetTools: Failed to execute Python path registration for: %s"), *PythonPath);
    }
}

void FQuickWidgetToolsModule::RegisterMenus()
{
    FToolMenuOwnerScoped OwnerScoped(this);

    UToolMenu* MainMenu = UToolMenus::Get()->ExtendMenu("LevelEditor.MainMenu");
    if (!MainMenu)
    {
        UE_LOG(LogTemp, Warning, TEXT("QuickWidgetTools: Failed to extend LevelEditor.MainMenu"));
        return;
    }

    FToolMenuSection& Section = MainMenu->FindOrAddSection("QuickWidgetToolsSection");

    Section.AddSubMenu(
        "QuickWidgetToolsRootMenu",
        LOCTEXT("QuickWidgetToolsMenuLabel", "Quick Widget Tools"),
        LOCTEXT("QuickWidgetToolsMenuTooltip", "Open editor utility widgets from the QuickWidgetTools plugin"),
        FNewToolMenuDelegate::CreateRaw(this, &FQuickWidgetToolsModule::PopulateWidgetsMenu),
        false,
        FSlateIcon()
    );
}

void FQuickWidgetToolsModule::PopulateWidgetsMenu(UToolMenu* Menu)
{
    if (!Menu)
    {
        return;
    }

    FToolMenuSection& Section = Menu->AddSection(
        "QuickWidgetToolsWidgetsSection",
        LOCTEXT("QuickWidgetToolsWidgetsHeading", "Editor Widgets")
    );

    TArray<FAssetData> WidgetAssets;
    FindEditorUtilityWidgets(WidgetAssets);

    if (WidgetAssets.Num() == 0)
    {
        FToolMenuEntry Entry = FToolMenuEntry::InitMenuEntry(
            NAME_None,
            LOCTEXT("NoWidgetsFound", "No Editor Utility Widgets Found"),
            LOCTEXT("NoWidgetsFoundTooltip", "No Editor Utility Widget Blueprints were found in /QuickWidgetTools/EditorWidgets"),
            FSlateIcon(),
            FToolUIActionChoice(),
            EUserInterfaceActionType::Button
        );

        Section.AddEntry(Entry);
        return;
    }

    WidgetAssets.Sort([](const FAssetData& A, const FAssetData& B)
        {
            return A.AssetName.LexicalLess(B.AssetName);
        });

    for (const FAssetData& Asset : WidgetAssets)
    {
        const FText Label = FText::FromName(Asset.AssetName);
        const FString ObjectPathString = Asset.GetSoftObjectPath().ToString();
        const FText Tooltip = FText::FromString(ObjectPathString);
        const FSoftObjectPath WidgetPath = Asset.GetSoftObjectPath();

        FToolMenuEntry Entry = FToolMenuEntry::InitMenuEntry(
            NAME_None,
            Label,
            Tooltip,
            FSlateIcon(),
            FToolUIActionChoice(
                FExecuteAction::CreateRaw(this, &FQuickWidgetToolsModule::LaunchEditorUtilityWidget, WidgetPath)
            ),
            EUserInterfaceActionType::Button
        );

        Section.AddEntry(Entry);
    }
}

void FQuickWidgetToolsModule::FindEditorUtilityWidgets(TArray<FAssetData>& OutAssets) const
{
    OutAssets.Reset();

    static const FName SearchPath(TEXT("/QuickWidgetTools/EditorWidgets"));

    FAssetRegistryModule& AssetRegistryModule =
        FModuleManager::LoadModuleChecked<FAssetRegistryModule>("AssetRegistry");

    IAssetRegistry& AssetRegistry = AssetRegistryModule.Get();

    const FTopLevelAssetPath WidgetBlueprintClassPath(
        TEXT("/Script/Blutility"),
        TEXT("EditorUtilityWidgetBlueprint")
    );

    FARFilter Filter;
    Filter.PackagePaths.Add(SearchPath);
    Filter.ClassPaths.Add(WidgetBlueprintClassPath);
    Filter.bRecursivePaths = true;
    Filter.bRecursiveClasses = true;

    AssetRegistry.GetAssets(Filter, OutAssets);

    UE_LOG(LogTemp, Log, TEXT("QuickWidgetTools: Found %d Editor Utility Widget(s) under %s"),
        OutAssets.Num(),
        *SearchPath.ToString()
    );
}

void FQuickWidgetToolsModule::LaunchEditorUtilityWidget(FSoftObjectPath WidgetPath) const
{
    if (!WidgetPath.IsValid())
    {
        UE_LOG(LogTemp, Warning, TEXT("QuickWidgetTools: Invalid widget path"));
        return;
    }

    UObject* LoadedObject = WidgetPath.TryLoad();
    if (!LoadedObject)
    {
        UE_LOG(LogTemp, Error, TEXT("QuickWidgetTools: Failed to load widget asset: %s"), *WidgetPath.ToString());
        return;
    }

    UEditorUtilityWidgetBlueprint* WidgetBlueprint = Cast<UEditorUtilityWidgetBlueprint>(LoadedObject);
    if (!WidgetBlueprint)
    {
        UE_LOG(LogTemp, Error, TEXT("QuickWidgetTools: Asset is not a UEditorUtilityWidgetBlueprint: %s"), *WidgetPath.ToString());
        return;
    }

    UEditorUtilitySubsystem* EditorUtilitySubsystem = GEditor
        ? GEditor->GetEditorSubsystem<UEditorUtilitySubsystem>()
        : nullptr;

    if (!EditorUtilitySubsystem)
    {
        UE_LOG(LogTemp, Error, TEXT("QuickWidgetTools: Could not get UEditorUtilitySubsystem"));
        return;
    }

    EditorUtilitySubsystem->SpawnAndRegisterTab(WidgetBlueprint);

    UE_LOG(LogTemp, Log, TEXT("QuickWidgetTools: Launched widget %s"), *WidgetPath.ToString());
}

#undef LOCTEXT_NAMESPACE

IMPLEMENT_MODULE(FQuickWidgetToolsModule, QuickWidgetTools)