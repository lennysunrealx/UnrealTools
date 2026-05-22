#pragma once

#include "CoreMinimal.h"
#include "Modules/ModuleManager.h"

// ============================================================================
// QuickPy Module
// ----------------------------------------------------------------------------
// Main editor module for the QuickPy plugin.
//
// Responsibilities:
// - Register the top-level QuickPy menu
// - Maintain the generated Python submenu tree
// - Run selected Python scripts
// - Open the project Python folder in the operating system file browser
// ============================================================================

class FQuickPyModule : public IModuleInterface
{
public:
	// Called when Unreal loads this plugin module.
	virtual void StartupModule() override;

	// Called when Unreal unloads this plugin module.
	virtual void ShutdownModule() override;

private:
	// ========================================================================
	// Menu Tree Data
	// ========================================================================
	struct FQuickPyMenuNode
	{
		// Child folders under this node.
		TMap<FString, TSharedPtr<FQuickPyMenuNode>> ChildFolders;

		// Python files that live directly inside this folder node.
		TArray<FString> PythonFiles;
	};

	// ========================================================================
	// Startup / Registration Helpers
	// ========================================================================

	// Ensure the project's Python folder exists.
	// If it does not exist yet, create it.
	void EnsureProjectPythonFolderExists() const;

	// Register the top-level QuickPy menu.
	void RegisterMenus();

	// Rebuild the static menu section that contains:
	// - Open Folder
	// - Refresh
	void RebuildStaticMenuSection();

	// ========================================================================
	// Refresh / Rebuild
	// ========================================================================

	// Called when the user clicks Refresh.
	// Logs the current Python folder scan and rebuilds the generated menu tree.
	void RefreshPythonIndex();

	// Clear and rebuild the generated Python submenu contents.
	void RebuildGeneratedPythonMenu();

	// Print a readable summary of the Python folder contents to the Output Log.
	void LogPythonIndexScan() const;

	// Find the already-registered QuickPy menu in ToolMenus.
	class UToolMenu* GetQuickPyMenu() const;

	// Remove previously generated Python menu content so rebuilds do not duplicate.
	void ClearGeneratedPythonMenu();

	// ========================================================================
	// Python File Discovery / Tree Building
	// ========================================================================

	// Recursively gather all .py files under the project's Python folder.
	void GatherPythonFiles(TArray<FString>& OutPythonFiles) const;

	// Convert the flat list of .py files into a nested tree structure that
	// matches the folder layout on disk.
	void BuildPythonMenuTree(const TArray<FString>& PythonFiles, FQuickPyMenuNode& OutRootNode) const;

	// Recursively convert a tree node into Unreal menu entries/submenus.
	void AddGeneratedPythonMenuEntries(
		class UToolMenu* ParentMenu,
		const FName SectionName,
		const FQuickPyMenuNode& CurrentNode,
		const FString& RelativePath
	);

	// Build a stable, sanitized Unreal menu name from a prefix + path/value.
	FName BuildMenuName(const FString& Prefix, const FString& Value);

	// ========================================================================
	// Python Folder / Script Actions
	// ========================================================================

	// Open the project's Python folder in the operating system file browser.
	void OpenPythonFolder();

	// Called when a generated Python script entry is clicked.
	// Executes the selected Python file.
	void OnPythonFileMenuEntryClicked(FString PythonFilePath);

private:
	// Tracks generated submenu names so they can be removed cleanly before
	// rebuilding the Python menu tree.
	TSet<FName> GeneratedMenuNames;
};