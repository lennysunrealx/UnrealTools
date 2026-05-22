#pragma once

#include "CoreMinimal.h"
#include "Modules/ModuleManager.h"

class UToolMenu;
class UEditorUtilityWidgetBlueprint;

class FQuickWidgetToolsModule : public IModuleInterface
{
public:
    virtual void StartupModule() override;
    virtual void ShutdownModule() override;

private:
    void RegisterMenus();
    void PopulateWidgetsMenu(UToolMenu* Menu);

    void FindEditorUtilityWidgets(TArray<FAssetData>& OutAssets) const;
    void LaunchEditorUtilityWidget(FSoftObjectPath WidgetPath) const;

    void RegisterPluginPythonPath();
    FString GetPluginPythonPath() const;
};