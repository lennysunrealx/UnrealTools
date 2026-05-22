import unreal

import mrg_callbacks_hero
import mrg_callbacks_render_info
import send_clickup_post_render


@unreal.uclass()
class MRGPostRenderScripts(unreal.MovieGraphScriptBase):
    LOG_PREFIX = "[QuickWidgetToolsMRG_PostRenderScripts]"

    def _log(self, message):
        unreal.log(f"{self.LOG_PREFIX} {message}")

    def _log_warning(self, message):
        unreal.log_warning(f"{self.LOG_PREFIX} Warning: {message}")

    def _log_error(self, message):
        unreal.log_error(f"{self.LOG_PREFIX} Error: {message}")

    def _run_child_callback(self, callback_label, callback_class, in_job_copy, in_output_data):
        try:
            self._log(f"Starting child callback: {callback_label}")

            callback_instance = callback_class()
            callback_instance.on_job_finished(in_job_copy, in_output_data)

            self._log(f"Finished child callback: {callback_label}")
            return True

        except Exception as exc:
            self._log_error(f"Child callback failed: {callback_label} | {exc}")
            return False

    @unreal.ufunction(override=True)
    def on_job_finished(self, in_job_copy, in_output_data):
        super().on_job_finished(in_job_copy, in_output_data)

        self._log("on_job_finished")

        try:
            success = in_output_data.success
        except Exception:
            success = False

        self._log(f"Render success: {success}")

        hero_ok = self._run_child_callback(
            "mrg_callbacks_hero.MRGHero",
            mrg_callbacks_hero.MRGHero,
            in_job_copy,
            in_output_data,
        )

        render_info_ok = self._run_child_callback(
            "mrg_callbacks_render_info.MRGRenderInfo",
            mrg_callbacks_render_info.MRGRenderInfo,
            in_job_copy,
            in_output_data,
        )

        clickup_ok = self._run_child_callback(
            "send_clickup_post_render.MRGSendClickUpPostRender",
            send_clickup_post_render.MRGSendClickUpPostRender,
            in_job_copy,
            in_output_data,
        )

        self._log(
            "Post-render summary: "
            f"hero_ok={hero_ok}, "
            f"render_info_ok={render_info_ok}, "
            f"clickup_ok={clickup_ok}"
        )