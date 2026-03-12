#include "QuickPyModule.h"

#include "HAL/FileManager.h"
#include "HAL/PlatformProcess.h"
#include "IPythonScriptPlugin.h"
#include "Misc/Paths.h"
#include "Modules/ModuleManager.h"
#include "ToolMenu.h"
#include "ToolMenuSection.h"
#include "ToolMenus.h"

#define LOCTEXT_NAMESPACE "FQuickPyModule"

// ============================================================================
// Constants / Logging
// ============================================================================

// Output Log category for QuickPy messages.
DEFINE_LOG_CATEGORY_STATIC(LogQuickPy, Log, All);

// ============================================================================
// Module Startup / Shutdown
// ============================================================================

void FQuickPyModule::StartupModule()
{
	// Make sure the project has a Python folder ready to use.
	EnsureProjectPythonFolderExists();

	// Ask ToolMenus to call RegisterMenus() once menu startup is ready.
	UToolMenus::RegisterStartupCallback(
		FSimpleMulticastDelegate::FDelegate::CreateRaw(this, &FQuickPyModule::RegisterMenus)
	);
}

void FQuickPyModule::ShutdownModule()
{
	// Remove our ToolMenus startup callback and unregister menu ownership.
	UToolMenus::UnRegisterStartupCallback(this);
	UToolMenus::UnregisterOwner(this);
}

// ============================================================================
// Project Python Folder Setup
// ============================================================================

void FQuickPyModule::EnsureProjectPythonFolderExists() const
{
	// Build the path to <ProjectRoot>/Python.
	const FString ProjectDirectory = FPaths::ProjectDir();
	const FString ProjectPythonDirectory = FPaths::Combine(ProjectDirectory, TEXT("Python"));

	// If it already exists, we are done.
	if (IFileManager::Get().DirectoryExists(*ProjectPythonDirectory))
	{
		return;
	}

	// Otherwise create the folder, including parent folders if needed.
	IFileManager::Get().MakeDirectory(*ProjectPythonDirectory, true);
}

// ============================================================================
// Menu Registration
// ============================================================================

void FQuickPyModule::RegisterMenus()
{
	// Scope menu ownership to this module.
	FToolMenuOwnerScoped OwnerScoped(this);

	UToolMenus* ToolMenus = UToolMenus::Get();
	if (!ToolMenus)
	{
		return;
	}

	// Extend Unreal's main editor menu bar.
	UToolMenu* MainMenu = ToolMenus->ExtendMenu("LevelEditor.MainMenu");
	if (!MainMenu)
	{
		return;
	}

	// Reuse the existing QuickPy menu if it already exists, otherwise create it.
	// This avoids duplicate top-level registration.
	static const FName QuickPyMenuName(TEXT("LevelEditor.MainMenu.QuickPy"));
	UToolMenu* QuickPySubMenu = ToolMenus->FindMenu(QuickPyMenuName);
	if (!QuickPySubMenu)
	{
		static const FName MainMenuSectionName(TEXT("MainMenu"));
		static const FName QuickPySubMenuEntryName(TEXT("QuickPy"));

		QuickPySubMenu = MainMenu->AddSubMenu(
			this,
			MainMenuSectionName,
			QuickPySubMenuEntryName,
			LOCTEXT("QuickPyMenuLabel", "QuickPy"),
			LOCTEXT("QuickPyMenuToolTip", "QuickPy tools.")
		);
	}

	if (!QuickPySubMenu)
	{
		return;
	}

	// Build the generated Python submenu first so it appears at the top.
	RebuildGeneratedPythonMenu();

	// Then rebuild the static section so Open Folder / Refresh appear below it.
	RebuildStaticMenuSection();
}

void FQuickPyModule::RebuildStaticMenuSection()
{
	UToolMenu* QuickPySubMenu = GetQuickPyMenu();
	if (!QuickPySubMenu)
	{
		return;
	}

	// Rebuild the static section cleanly so Open Folder and Refresh do not duplicate.
	static const FName QuickPyStaticSectionName(TEXT("QuickPy.Static"));
	if (QuickPySubMenu->FindSection(QuickPyStaticSectionName))
	{
		QuickPySubMenu->RemoveSection(QuickPyStaticSectionName);
	}

	FToolMenuSection& StaticSection = QuickPySubMenu->AddSection(QuickPyStaticSectionName);

	// Static action: Open the project Python folder in the OS file browser.
	StaticSection.AddMenuEntry(
		"OpenPythonFolder",
		LOCTEXT("OpenPythonFolderLabel", "Open Folder"),
		LOCTEXT("OpenPythonFolderToolTip", "Open the project Python folder."),
		FSlateIcon(),
		FUIAction(FExecuteAction::CreateRaw(this, &FQuickPyModule::OpenPythonFolder))
	);

	// Static action: Refresh the Python folder scan and rebuild the generated menu.
	StaticSection.AddMenuEntry(
		"RefreshPythonIndex",
		LOCTEXT("RefreshPythonIndexLabel", "Refresh"),
		LOCTEXT("RefreshPythonIndexToolTip", "Scan and list Python folders and .py files."),
		FSlateIcon(),
		FUIAction(FExecuteAction::CreateRaw(this, &FQuickPyModule::RefreshPythonIndex))
	);
}

// ============================================================================
// Refresh / Generated Menu Rebuild
// ============================================================================

void FQuickPyModule::RefreshPythonIndex()
{
	// Log what currently exists on disk.
	LogPythonIndexScan();

	// Rebuild the generated Python menu so changes appear immediately.
	RebuildGeneratedPythonMenu();

	// Rebuild the static section after the generated section so Python stays at the top.
	RebuildStaticMenuSection();
}

void FQuickPyModule::RebuildGeneratedPythonMenu()
{
	UToolMenus* ToolMenus = UToolMenus::Get();
	if (!ToolMenus)
	{
		return;
	}

	UToolMenu* QuickPyMenu = GetQuickPyMenu();
	if (!QuickPyMenu)
	{
		return;
	}

	// Remove previously generated content so this rebuild stays clean and repeatable.
	ClearGeneratedPythonMenu();

	// Remove and recreate the generated root section that contains the Python submenu.
	static const FName QuickPyGeneratedRootSectionName(TEXT("QuickPy.GeneratedRoot"));
	if (QuickPyMenu->FindSection(QuickPyGeneratedRootSectionName))
	{
		QuickPyMenu->RemoveSection(QuickPyGeneratedRootSectionName);
	}

	// Create the generated root submenu: QuickPy > Python
	static const FName QuickPyPythonMenuName(TEXT("LevelEditor.MainMenu.QuickPy.Python"));
	UToolMenu* PythonMenu = QuickPyMenu->AddSubMenu(
		this,
		QuickPyGeneratedRootSectionName,
		QuickPyPythonMenuName,
		LOCTEXT("QuickPyPythonSubMenuLabel", "Python"),
		LOCTEXT("QuickPyPythonSubMenuToolTip", "QuickPy Python scripts.")
	);

	if (!PythonMenu)
	{
		return;
	}

	// Gather .py files from disk.
	TArray<FString> PythonFiles;
	GatherPythonFiles(PythonFiles);

	// Build a folder tree from that list.
	FQuickPyMenuNode RootNode;
	BuildPythonMenuTree(PythonFiles, RootNode);

	// Turn the tree into nested menu entries under QuickPy > Python.
	static const FName QuickPyGeneratedSectionName(TEXT("QuickPy.Generated"));
	AddGeneratedPythonMenuEntries(PythonMenu, QuickPyGeneratedSectionName, RootNode, TEXT(""));

	// Refresh the visible menu widget so the user sees the update immediately.
	ToolMenus->RefreshMenuWidget(QuickPyMenu->GetMenuName());
}

UToolMenu* FQuickPyModule::GetQuickPyMenu() const
{
	// Look up the QuickPy menu by its registered ToolMenus path.
	return UToolMenus::Get()->FindMenu("LevelEditor.MainMenu.QuickPy");
}

void FQuickPyModule::ClearGeneratedPythonMenu()
{
	UToolMenus* ToolMenus = UToolMenus::Get();
	if (!ToolMenus)
	{
		return;
	}

	// Remove all dynamically created child menus that we tracked during prior builds.
	for (const FName& MenuName : GeneratedMenuNames)
	{
		ToolMenus->RemoveMenu(MenuName);
	}
	GeneratedMenuNames.Reset();

	UToolMenu* QuickPyMenu = GetQuickPyMenu();
	if (!QuickPyMenu)
	{
		return;
	}

	// Remove the generated root section from the QuickPy menu.
	static const FName QuickPyGeneratedRootSectionName(TEXT("QuickPy.GeneratedRoot"));
	if (QuickPyMenu->FindSection(QuickPyGeneratedRootSectionName))
	{
		QuickPyMenu->RemoveSection(QuickPyGeneratedRootSectionName);
	}

	// Remove the generated section inside the Python submenu if it exists.
	UToolMenu* PythonMenu = ToolMenus->FindMenu("LevelEditor.MainMenu.QuickPy.Python");
	if (!PythonMenu)
	{
		return;
	}

	static const FName QuickPyGeneratedSectionName(TEXT("QuickPy.Generated"));
	if (PythonMenu->FindSection(QuickPyGeneratedSectionName))
	{
		PythonMenu->RemoveSection(QuickPyGeneratedSectionName);
	}
}

// ============================================================================
// Refresh Logging
// ============================================================================

void FQuickPyModule::LogPythonIndexScan() const
{
	// Point to the project's Python folder.
	const FString ProjectPythonDirectory = FPaths::Combine(FPaths::ProjectDir(), TEXT("Python"));

	TArray<FString> FoundDirectories;
	TArray<FString> FoundPythonFiles;

	IFileManager& FileManager = IFileManager::Get();

	// Recursively gather all folders under Python.
	FileManager.FindFilesRecursive(
		FoundDirectories,
		*ProjectPythonDirectory,
		TEXT("*"),
		false,
		true,
		false
	);

	// Recursively gather all .py files under Python.
	FileManager.FindFilesRecursive(
		FoundPythonFiles,
		*ProjectPythonDirectory,
		TEXT("*.py"),
		true,
		false,
		false
	);

	// If nothing exists, log a short message and stop.
	const bool bFoundAnything = FoundDirectories.Num() > 0 || FoundPythonFiles.Num() > 0;
	if (!bFoundAnything)
	{
		UE_LOG(LogQuickPy, Display, TEXT("QuickPy Found Nothing"));
		return;
	}

	// Sort results so the log output stays stable and easy to scan.
	FoundDirectories.Sort();
	FoundPythonFiles.Sort();

	// Helper: turn a full path into a path relative to the Python root folder.
	auto MakeRelativeToPythonRoot = [&ProjectPythonDirectory](const FString& FullPath)
		{
			FString RelativePath = FullPath;
			FPaths::MakePathRelativeTo(RelativePath, *ProjectPythonDirectory);
			FPaths::NormalizeFilename(RelativePath);
			return RelativePath;
		};

	UE_LOG(LogQuickPy, Display, TEXT("QuickPy Refresh Results"));
	UE_LOG(LogQuickPy, Display, TEXT("Root: Python"));

	UE_LOG(LogQuickPy, Display, TEXT("Folders and Subfolders (%d):"), FoundDirectories.Num());
	for (const FString& DirectoryPath : FoundDirectories)
	{
		const FString RelativeDirectoryPath = MakeRelativeToPythonRoot(DirectoryPath);

		// Use the number of path segments to decide whether this is a direct child
		// folder or a deeper nested subfolder.
		TArray<FString> RelativeSegments;
		RelativeDirectoryPath.ParseIntoArray(RelativeSegments, TEXT("/"), true);
		const bool bIsDirectChild = RelativeSegments.Num() <= 1;

		UE_LOG(
			LogQuickPy,
			Display,
			TEXT("  [%s] %s"),
			bIsDirectChild ? TEXT("Folder") : TEXT("Subfolder"),
			*RelativeDirectoryPath
		);
	}

	UE_LOG(LogQuickPy, Display, TEXT("Python Files (%d):"), FoundPythonFiles.Num());
	for (const FString& PythonFilePath : FoundPythonFiles)
	{
		const FString RelativePythonFilePath = MakeRelativeToPythonRoot(PythonFilePath);
		UE_LOG(LogQuickPy, Display, TEXT("  [PyFile] %s"), *RelativePythonFilePath);
	}
}

// ============================================================================
// Python File Discovery
// ============================================================================

void FQuickPyModule::GatherPythonFiles(TArray<FString>& OutPythonFiles) const
{
	// Point to the project-level Python folder.
	const FString ProjectPythonDirectory = FPaths::Combine(FPaths::ProjectDir(), TEXT("Python"));

	OutPythonFiles.Reset();

	// Recursively gather every .py file under that folder.
	IFileManager::Get().FindFilesRecursive(
		OutPythonFiles,
		*ProjectPythonDirectory,
		TEXT("*.py"),
		true,
		false,
		false
	);

	// Sort to keep menu generation stable and alphabetized.
	OutPythonFiles.Sort();
}

// ============================================================================
// Python Menu Tree Construction
// ============================================================================

void FQuickPyModule::BuildPythonMenuTree(const TArray<FString>& PythonFiles, FQuickPyMenuNode& OutRootNode) const
{
	// Base folder we want all paths to be relative to.
	const FString ProjectPythonDirectory = FPaths::Combine(FPaths::ProjectDir(), TEXT("Python"));
	static const FString PythonRootSegment(TEXT("Python/"));
	static const FString PythonRootFolder(TEXT("Python"));

	for (const FString& PythonFilePath : PythonFiles)
	{
		// Convert the file path to a path relative to the Python root.
		FString RelativeFilePath = PythonFilePath;
		FPaths::MakePathRelativeTo(RelativeFilePath, *ProjectPythonDirectory);
		FPaths::NormalizeFilename(RelativeFilePath);

		// Defensive cleanup to avoid accidentally creating Python > Python > ...
		if (RelativeFilePath.StartsWith(PythonRootSegment))
		{
			RelativeFilePath.RightChopInline(PythonRootSegment.Len(), EAllowShrinking::No);
		}
		else if (RelativeFilePath.Equals(PythonRootFolder))
		{
			RelativeFilePath.Reset();
		}

		// Get just the folder portion of the relative path and split it into segments.
		FString RelativeDirectoryPath = FPaths::GetPath(RelativeFilePath);
		TArray<FString> FolderSegments;
		if (!RelativeDirectoryPath.IsEmpty())
		{
			RelativeDirectoryPath.ParseIntoArray(FolderSegments, TEXT("/"), true);
		}

		// Walk or create tree nodes for each folder segment.
		FQuickPyMenuNode* CurrentNode = &OutRootNode;
		for (const FString& FolderName : FolderSegments)
		{
			TSharedPtr<FQuickPyMenuNode>& ChildNode = CurrentNode->ChildFolders.FindOrAdd(FolderName);
			if (!ChildNode.IsValid())
			{
				ChildNode = MakeShared<FQuickPyMenuNode>();
			}

			CurrentNode = ChildNode.Get();
		}

		// Store the file in the final node for this folder.
		CurrentNode->PythonFiles.Add(PythonFilePath);
	}
}

// ============================================================================
// Generated Menu Creation
// ============================================================================

void FQuickPyModule::AddGeneratedPythonMenuEntries(
	UToolMenu* ParentMenu,
	const FName SectionName,
	const FQuickPyMenuNode& CurrentNode,
	const FString& RelativePath
)
{
	// Get or create the section inside this menu that will hold generated entries.
	FToolMenuSection& Section = ParentMenu->FindOrAddSection(SectionName);

	// Gather and sort child folder names so the menu order stays stable.
	TArray<FString> FolderNames;
	CurrentNode.ChildFolders.GetKeys(FolderNames);
	FolderNames.Sort();

	// First create child folder submenus.
	for (const FString& FolderName : FolderNames)
	{
		const FString ChildRelativePath = RelativePath.IsEmpty()
			? FolderName
			: FPaths::Combine(RelativePath, FolderName);

		// Build a unique, Unreal-safe internal menu name for this child submenu.
		const FName ChildMenuName = BuildMenuName(TEXT("QuickPy.Generated.Folder"), ChildRelativePath);

		UToolMenu* ChildSubMenu = ParentMenu->AddSubMenu(
			this,
			SectionName,
			ChildMenuName,
			FText::FromString(FolderName),
			FText::Format(
				LOCTEXT("QuickPyGeneratedFolderToolTip", "QuickPy scripts under {0}"),
				FText::FromString(ChildRelativePath)
			)
		);

		// Track this generated submenu so it can be removed during the next rebuild.
		GeneratedMenuNames.Add(ChildSubMenu->GetMenuName());

		// Recurse into the child folder node to add more subfolders/files beneath it.
		const TSharedPtr<FQuickPyMenuNode> ChildNode = CurrentNode.ChildFolders.FindChecked(FolderName);
		if (ChildNode.IsValid())
		{
			AddGeneratedPythonMenuEntries(
				ChildSubMenu,
				SectionName,
				*ChildNode,
				ChildRelativePath
			);
		}
	}

	// Then create clickable menu entries for the Python files in this folder.
	for (const FString& PythonFilePath : CurrentNode.PythonFiles)
	{
		// Use the base filename (without .py) as the visible menu label.
		const FString ScriptName = FPaths::GetBaseFilename(PythonFilePath);

		Section.AddMenuEntry(
			BuildMenuName(TEXT("QuickPy.Generated.File"), PythonFilePath),
			FText::FromString(ScriptName),
			FText::FromString(PythonFilePath),
			FSlateIcon(),
			FUIAction(FExecuteAction::CreateRaw(this, &FQuickPyModule::OnPythonFileMenuEntryClicked, PythonFilePath))
		);
	}
}

FName FQuickPyModule::BuildMenuName(const FString& Prefix, const FString& Value)
{
	// Sanitize a path/value into something stable for Unreal's internal menu naming.
	FString SanitizedValue = Value;
	SanitizedValue.ReplaceInline(TEXT("\\"), TEXT("/"));
	SanitizedValue.ReplaceInline(TEXT("/"), TEXT("."));
	SanitizedValue.ReplaceInline(TEXT(" "), TEXT("_"));
	SanitizedValue.ReplaceInline(TEXT(":"), TEXT("_"));

	return FName(*FString::Printf(TEXT("%s.%s"), *Prefix, *SanitizedValue));
}

// ============================================================================
// Python Folder / Script Actions
// ============================================================================

void FQuickPyModule::OpenPythonFolder()
{
	// Build the path to the project's Python folder.
	const FString ProjectPythonDirectory = FPaths::Combine(FPaths::ProjectDir(), TEXT("Python"));

	// Convert it to a full absolute path for the OS file browser.
	const FString FullProjectPythonDirectory = FPaths::ConvertRelativePathToFull(ProjectPythonDirectory);

	// Make sure it exists before trying to open it.
	if (!IFileManager::Get().DirectoryExists(*FullProjectPythonDirectory))
	{
		UE_LOG(LogQuickPy, Error, TEXT("QuickPy failed to open Python folder (folder missing): %s"), *FullProjectPythonDirectory);
		return;
	}

	UE_LOG(LogQuickPy, Display, TEXT("QuickPy opening Python folder: %s"), *FullProjectPythonDirectory);

	// Open the folder in the OS file browser.
	FPlatformProcess::ExploreFolder(*FullProjectPythonDirectory);
}

void FQuickPyModule::OnPythonFileMenuEntryClicked(FString PythonFilePath)
{
	// Make sure the script file still exists before trying to run it.
	if (!IFileManager::Get().FileExists(*PythonFilePath))
	{
		UE_LOG(LogQuickPy, Error, TEXT("QuickPy failed to run script (file missing): %s"), *PythonFilePath);
		return;
	}

	UE_LOG(LogQuickPy, Display, TEXT("QuickPy running Python script: %s"), *PythonFilePath);

	// Load the Python plugin module and make sure Python is available.
	IPythonScriptPlugin* PythonScriptPlugin = FModuleManager::LoadModulePtr<IPythonScriptPlugin>(TEXT("PythonScriptPlugin"));
	if (!PythonScriptPlugin || !PythonScriptPlugin->IsPythonAvailable())
	{
		UE_LOG(LogQuickPy, Error, TEXT("QuickPy failed to run script (Python plugin unavailable): %s"), *PythonFilePath);
		return;
	}

	// Build a command that executes the selected Python file.
	FPythonCommandEx PythonCommand;
	PythonCommand.ExecutionMode = EPythonCommandExecutionMode::ExecuteFile;
	PythonCommand.FileExecutionScope = EPythonFileExecutionScope::Private;
	PythonCommand.Command = PythonFilePath;

	// Execute the script and log success/failure.
	if (!PythonScriptPlugin->ExecPythonCommandEx(PythonCommand))
	{
		UE_LOG(LogQuickPy, Error, TEXT("QuickPy failed to run script: %s"), *PythonFilePath);
		if (!PythonCommand.CommandResult.IsEmpty())
		{
			UE_LOG(LogQuickPy, Error, TEXT("QuickPy Python error details: %s"), *PythonCommand.CommandResult);
		}
		return;
	}

	UE_LOG(LogQuickPy, Display, TEXT("QuickPy script succeeded: %s"), *PythonFilePath);
}

#undef LOCTEXT_NAMESPACE

IMPLEMENT_MODULE(FQuickPyModule, QuickPy)