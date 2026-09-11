/**
 * 模板绑定自检：`npm run build` 只能证明 SFC 能编译，不能证明模板里的
 * 标识符真的存在于 <script setup> 中（未定义标识符只会在运行时被解析成
 * `_ctx.xxx` → 界面上静默变成空白）。
 *
 * 本脚本用 @vue/compiler-sfc 把每个 .vue 编译成渲染函数，然后扫描产物里的
 * `_ctx.xxx` 与 `_resolveComponent(...)`：
 *   - `_ctx.xxx`            → 模板引用了 script setup 里没有的名字
 *   - `_resolveComponent()` → 模板用了未 import 的组件，运行时会告警并渲染失败
 *
 * 用法： cd frontend && npm run check:bindings
 */
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'
import { dirname } from 'node:path'
import { parse, compileScript } from '@vue/compiler-sfc'

const here = dirname(fileURLToPath(import.meta.url))
const root = join(here, '..')

/** 编译器白名单里的全局量，出现 `_ctx.` 之外的形式，这里列出以防误报。 */
const IGNORE = new Set(['$event', '$slots', '$props', '$attrs', '$refs', '$el', '$options'])

function walk(dir, acc = []) {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name)
    if (statSync(full).isDirectory()) walk(full, acc)
    else if (name.endsWith('.vue')) acc.push(full)
  }
  return acc
}

let files = 0
let problems = 0

for (const file of walk(join(root, 'src'))) {
  const rel = relative(root, file).replace(/\\/g, '/')
  const source = readFileSync(file, 'utf8')
  files += 1

  const { descriptor, errors } = parse(source, { filename: rel })
  if (errors.length) {
    problems += errors.length
    for (const e of errors) console.log(`FAIL ${rel}: 解析失败 ${e.message}`)
    continue
  }
  if (!descriptor.template) continue

  let code
  try {
    code = compileScript(descriptor, { id: rel, inlineTemplate: true }).content
  } catch (err) {
    problems += 1
    console.log(`FAIL ${rel}: 编译失败 ${err.message}`)
    continue
  }

  const missing = new Set()
  for (const m of code.matchAll(/_ctx\.([A-Za-z_$][\w$]*)/g)) {
    const name = m[1]
    if (!IGNORE.has(name)) missing.add(name)
  }
  if (missing.size) {
    problems += missing.size
    console.log(`FAIL ${rel}: 模板引用了未定义标识符 -> ${[...missing].sort().join(', ')}`)
  }

  const comps = new Set()
  for (const m of code.matchAll(/_resolveComponent\("([^"]+)"\)/g)) comps.add(m[1])
  if (comps.size) {
    problems += comps.size
    console.log(`WARN ${rel}: 模板使用了未 import 的组件 -> ${[...comps].sort().join(', ')}`)
  }
}

console.log(`\n检查 ${files} 个 SFC，发现 ${problems} 处问题`)
process.exit(problems ? 1 : 0)
