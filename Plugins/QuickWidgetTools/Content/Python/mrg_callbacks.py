import unreal


@unreal.uclass()
class MRGCallbacks(unreal.MovieGraphScriptBase):

    @unreal.ufunction(override=True)
    def on_job_start(self, in_job_copy):
        super().on_job_start(in_job_copy)
        unreal.log("[QuickWidgetToolsMRG] on_job_start")

    @unreal.ufunction(override=True)
    def on_job_finished(self, in_job_copy, in_output_data):
        super().on_job_finished(in_job_copy, in_output_data)

        # Epic notes this fires at the very end of the Movie Graph Pipeline.
        # Output files should already be written to disk at this point.
        unreal.log("[QuickWidgetToolsMRG] on_job_finished")

        try:
            # Success flag
            success = in_output_data.success
        except Exception:
            success = False

        unreal.log(f"[QuickWidgetToolsMRG] Render success: {success}")

        # Try to print all output file paths
        # The exact nested data can vary a bit by pipeline/output setup,
        # so keep this defensive.
        try:
            graph_data = in_output_data.graph_data
            for branch_name, branch_data in graph_data.items():
                unreal.log(f"[QuickWidgetToolsMRG] Branch: {branch_name}")

                try:
                    for layer_identifier, layer_data in branch_data.items():
                        unreal.log(f"[QuickWidgetToolsMRG]   Layer: {layer_identifier}")

                        try:
                            for file_path in layer_data.file_paths:
                                unreal.log(f"[QuickWidgetToolsMRG]     File: {file_path}")
                        except Exception:
                            unreal.log_warning(
                                f"[QuickWidgetToolsMRG]     Could not read file_paths for layer: {layer_identifier}"
                            )
                except Exception:
                    unreal.log_warning(
                        f"[QuickWidgetToolsMRG]   Could not iterate branch data for: {branch_name}"
                    )

        except Exception as e:
            unreal.log_warning(f"[QuickWidgetToolsMRG] Could not inspect output data: {e}")