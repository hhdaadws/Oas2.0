import { reactive } from "vue";
import { ElMessage } from "element-plus";
import { commonApi, parseApiError } from "../lib/http";
import { userTypeLabel } from "../lib/helpers";

export function useTaskTemplates() {
  const templateCache = reactive({});
  const loadingTemplates = reactive({ value: false });

  async function ensureTaskTemplates(userType, userTypeOptionsRef) {
    const normalizedType = userType || "daily";
    if (templateCache[normalizedType]) return templateCache[normalizedType];
    loadingTemplates.value = true;
    try {
      const response = await commonApi.taskTemplates(normalizedType);
      templateCache[normalizedType] = {
        order: response.order || [],
        defaultConfig: response.default_config || {},
      };
      if (userTypeOptionsRef && Array.isArray(response.supported_user_types) && response.supported_user_types.length > 0) {
        userTypeOptionsRef.value = response.supported_user_types.map((item) => ({
          value: item,
          label: userTypeLabel(item),
        }));
      }
      return templateCache[normalizedType];
    } catch (error) {
      ElMessage.error(parseApiError(error));
      return { order: [], defaultConfig: {} };
    } finally {
      loadingTemplates.value = false;
    }
  }

  return { templateCache, loadingTemplates, ensureTaskTemplates };
}
