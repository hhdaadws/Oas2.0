import request from './request'

// 勾协库列表
export function listCoopAccounts(params = {}) {
  return request({
    url: '/coop/accounts',
    method: 'get',
    params
  })
}

// 创建勾协库账号
export function createCoopAccount(data) {
  return request({
    url: '/coop/accounts',
    method: 'post',
    data
  })
}

// 更新勾协库账号
export function updateCoopAccount(id, data) {
  return request({
    url: `/coop/accounts/${id}`,
    method: 'put',
    data
  })
}

// 删除勾协库账号
export function deleteCoopAccount(id) {
  return request({
    url: `/coop/accounts/${id}`,
    method: 'delete'
  })
}

// 批量导入
export function batchImportCoopAccounts(lines) {
  return request({
    url: '/coop/accounts/batch-import',
    method: 'post',
    data: { lines }
  })
}

