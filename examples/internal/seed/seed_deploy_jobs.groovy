// Job DSL — UI SoT for deploy Pipeline params.
// CLUSTER_ID Phase 0–5 + PHASES ADR 010 cascade + LIMIT ADR 011 cascade (Phase 3).
// Bound from seed Jenkinsfile additionalParameters (Job DSL plugin).
// Contract: docs/jenkins-seed.md

import java.util.ArrayList

def rawIds = (binding.hasVariable('CLUSTER_IDS') ? CLUSTER_IDS : '') as String
def ids = rawIds.readLines().collect { it.trim() }.findAll { it }
if (ids.isEmpty()) {
    throw new IllegalStateException('CLUSTER_IDS is empty — seed must fail before Job DSL')
}

def agentRaw = (binding.hasVariable('AGENT_CHOICES') ? AGENT_CHOICES : '') as String
def agents = new LinkedHashSet()
agents.add('built-in')
agentRaw.readLines().collect { it.trim() }.findAll { it }.each { agents.add(it) }
// Job DSL often can read controller computers even when Pipeline sandbox cannot.
try {
    def j = jenkins.model.Jenkins.getInstanceOrNull()
    if (j == null) {
        j = jenkins.model.Jenkins.instance
    }
    j?.computers?.each { c ->
        def n = c?.name?.toString()
        if (!n?.trim() || n == 'master' || n == '(master)') {
            agents.add('built-in')
        } else {
            agents.add(n)
        }
    }
    println "seed_deploy_jobs: AGENT from Jenkins computers + AGENT_CHOICES → ${agents.size()} name(s)"
} catch (Throwable t) {
    println "seed_deploy_jobs: Jenkins computer merge skipped (${t.class.simpleName}); using AGENT_CHOICES only"
}
agents = (['built-in'] + agents.findAll { it != 'built-in' }.sort()) as ArrayList

def specsRaw = (binding.hasVariable('DEPLOY_SPECS') ? DEPLOY_SPECS : '') as String
def specs = specsRaw.readLines().collect { it.trim() }.findAll { it && !it.startsWith('#') }
if (specs.isEmpty()) {
    throw new IllegalStateException('DEPLOY_SPECS is empty')
}

def clusterctlUrl = (binding.hasVariable('CLUSTERCTL_GIT_URL') ? CLUSTERCTL_GIT_URL : '') as String
def clusterctlRef = (binding.hasVariable('CLUSTERCTL_GIT_REF') ? CLUSTERCTL_GIT_REF : 'main') as String
def gitCred = (binding.hasVariable('GIT_SSH_CREDENTIALS_ID') ? GIT_SSH_CREDENTIALS_ID : '') as String
def invUrlDefault = (binding.hasVariable('INVENTORY_GIT_URL_DEFAULT') ? INVENTORY_GIT_URL_DEFAULT : '') as String

def escapeSq = { String s ->
    // Keep single-quoted Groovy literals intact inside the embedded switch
    // (newlines in inventory hostname: would otherwise break the whole script).
    s.replace('\\', '\\\\')
        .replace('\'', '\\\'')
        .replace('\r', '\\r')
        .replace('\n', '\\n')
}

// --- PHASES map (ADR 010) → sandbox-friendly switch (no JsonSlurper at form-render)
def phasesJson = (binding.hasVariable('CLUSTER_PHASES_JSON') ? CLUSTER_PHASES_JSON : '{}') as String
if (!phasesJson?.trim()) {
    phasesJson = '{}'
}
def phasesMap = [:]
def parsedPhases = new groovy.json.JsonSlurper().parseText(phasesJson)
if (parsedPhases instanceof Map) {
    phasesMap = parsedPhases
} else {
    throw new IllegalStateException('CLUSTER_PHASES_JSON must be a JSON object')
}

def phasesSwitchBody = new StringBuilder()
phasesMap.each { cid, phases ->
    if (!(phases instanceof List) || phases.isEmpty()) {
        return
    }
    def listLit = phases.collect { p -> "'${escapeSq(p.toString())}'" }.join(', ')
    phasesSwitchBody.append("  case '${escapeSq(cid.toString())}': return [${listLit}]\n")
}
def phasesReactiveScript = '''
def cid = null
try {
  cid = CLUSTER_ID?.toString()
} catch (Throwable ignored) {
}
if (!cid && binding.hasVariable('CLUSTER_ID')) {
  cid = binding.getVariable('CLUSTER_ID')?.toString()
}
if (!cid) {
  return []
}
switch (cid) {
''' + phasesSwitchBody.toString() + '''
  default: return []
}
'''

// --- LIMITS map (ADR 011) → sandbox-friendly switch (no JsonSlurper at form-render)
// Same artifact as cluster-limits.json. Prefer UI map value→label (hierarchical);
// flat lists still accepted for older artifacts.
def limitsJson = (binding.hasVariable('CLUSTER_LIMITS_JSON') ? CLUSTER_LIMITS_JSON : '{}') as String
if (!limitsJson?.trim()) {
    limitsJson = '{}'
}
def limitsMap = [:]
def parsedLimits = new groovy.json.JsonSlurper().parseText(limitsJson)
if (parsedLimits instanceof Map) {
    limitsMap = parsedLimits
} else {
    throw new IllegalStateException('CLUSTER_LIMITS_JSON must be a JSON object')
}

def limitsSwitchBody = new StringBuilder()
limitsMap.each { cid, names ->
    // Preferred: ordered [{value, label}, …] (hierarchy survives JsonSlurper).
    if (names instanceof List && !names.isEmpty() && names[0] instanceof Map) {
        def pairs = names.collect { entry ->
            def value = entry.get('value')?.toString()
            def label = entry.get('label')?.toString()
            if (!value) {
                return null
            }
            if (!label) {
                label = value
            }
            "'${escapeSq(value)}':'${escapeSq(label)}'"
        }.findAll { it }.join(', ')
        if (!pairs) {
            return
        }
        limitsSwitchBody.append("  case '${escapeSq(cid.toString())}': return [${pairs}]\n")
        return
    }
    // Legacy flat list of strings → label == value.
    if (names instanceof List && !names.isEmpty()) {
        def pairs = names.collect { n ->
            def s = n.toString()
            "'${escapeSq(s)}':'${escapeSq(s)}'"
        }.join(', ')
        limitsSwitchBody.append("  case '${escapeSq(cid.toString())}': return [${pairs}]\n")
        return
    }
    // Legacy object map value→label (order not guaranteed after JsonSlurper).
    if (names instanceof Map && !names.isEmpty()) {
        def pairs = names.collect { k, v ->
            "'${escapeSq(k.toString())}':'${escapeSq(v.toString())}'"
        }.join(', ')
        limitsSwitchBody.append("  case '${escapeSq(cid.toString())}': return [${pairs}]\n")
    }
}
def limitsReactiveScript = '''
def cid = null
try {
  cid = CLUSTER_ID?.toString()
} catch (Throwable ignored) {
}
if (!cid && binding.hasVariable('CLUSTER_ID')) {
  cid = binding.getVariable('CLUSTER_ID')?.toString()
}
if (!cid) {
  return [:]
}
switch (cid) {
''' + limitsSwitchBody.toString() + '''
  default: return [:]
}
'''
if (!clusterctlUrl?.trim()) {
    throw new IllegalStateException('CLUSTERCTL_GIT_URL is required')
}

specs.each { line ->
    def parts = line.split('\\|', 2)
    if (parts.length != 2) {
        throw new IllegalStateException("DEPLOY_SPECS line must be JOB_NAME|scriptPath, got: ${line}")
    }
    def jobName = parts[0].trim()
    // Do not name this `scriptPath` — it shadows Job DSL method scriptPath(…).
    def jfScript = parts[1].trim()
    if (!jobName || !jfScript) {
        throw new IllegalStateException("invalid DEPLOY_SPECS line: ${line}")
    }
    // Docker sample only — bare-agent .local does not override execution.tag via env.
    def dockerSample = jfScript.endsWith('Jenkinsfile') && !jfScript.endsWith('Jenkinsfile.local')

    pipelineJob(jobName) {
        displayName(jobName)
        description(
            'atlas-clusterctl deploy sample. UI parameters (incl. CLUSTER_ID choice + ' +
            'PHASES / LIMIT Active Choices cascades) owned by atlas-clusterctl-seed. ' +
            'Each seed Build rewrites params + SCM. Requires Active Choices (uno-choice).'
        )
        parameters {
            // AGENT: choice from seed-time controller computer list (Pipeline label).
            // Re-run seed after agents are added/removed. No Active Choices / no filter box.
            choiceParam(
                'AGENT',
                new ArrayList(agents),
                'Jenkins agent node name (Pipeline label). From inventory jenkins ' +
                'hostnames at last seed (+ controller computers when readable).'
            )
            choiceParam(
                'CLUSTER_ID',
                new ArrayList(ids),
                'Deployable leaf under clusters/<env>/<name>/ (seeded from inventory)'
            )
            stringParam(
                'INVENTORY_GIT_URL',
                invUrlDefault,
                'Optional: inventory git URL (ssh://git@host/path preferred). Empty = skip checkout'
            )
            stringParam(
                'INVENTORY_GIT_REF',
                'main',
                'Inventory branch name for INVENTORY_GIT_URL (not a commit SHA; shallow --branch)'
            )
            stringParam('INVENTORY_DIR', 'atlas-inventory', 'Checkout directory for inventory')
            // PHASES: Active Choices cascade off CLUSTER_ID (ADR 010 / path C).
            // Requires controller plugin uno-choice. Empty selection = plan SoT.
            activeChoiceReactiveParam('PHASES') {
                description(
                    'YAML short names for selected CLUSTER_ID (ADR 010). ' +
                    'None checked = plan SoT (no --phases). Multi = CSV a,b,c. ' +
                    'With TAGS/LIMIT check one NAME. Re-run seed after phases: changes.'
                )
                filterable(false)
                // Job DSL enum: SINGLE_SELECT | MULTI_SELECT | CHECKBOX | RADIO
                choiceType('CHECKBOX')
                groovyScript {
                    script(phasesReactiveScript)
                    // Visible marker if Script Approval blocks the primary script.
                    fallbackScript('return ["__PHASES_SCRIPT_BLOCKED_APPROVE_IN_JENKINS__"]')
                }
                referencedParameter('CLUSTER_ID')
            }
            stringParam(
                'TAGS',
                '',
                'Optional ansible --tags for Run (ADR 009). Empty or all = catalog.'
            )
            // LIMIT: Active Choices cascade off CLUSTER_ID (ADR 011).
            // Empty selection = omit --limit. Requires uno-choice (same as PHASES).
            activeChoiceReactiveParam('LIMIT') {
                description(
                    'Inventory groups with nested host keys for selected CLUSTER_ID ' +
                    '(ADR 011). Group row = --limit group; host row = --limit key ' +
                    '(label may show hostname: DNS). None checked = omit --limit. ' +
                    'Multi = CSV. Non-empty → single-phase PHASES (ADR 009). ' +
                    'Advanced patterns (and / tilde / bang) not in UI — use CLI. ' +
                    'Re-run seed after hosts/group changes.'
                )
                filterable(false)
                // Job DSL enum: SINGLE_SELECT | MULTI_SELECT | CHECKBOX | RADIO
                choiceType('CHECKBOX')
                groovyScript {
                    script(limitsReactiveScript)
                    // Visible marker if Script Approval blocks the primary script
                    // (silent return [] looks like "no catalog" / missing checkboxes).
                    fallbackScript('return ["__LIMIT_SCRIPT_BLOCKED_APPROVE_IN_JENKINS__"]')
                }
                referencedParameter('CLUSTER_ID')
            }
            stringParam(
                'EXTRA_VARS',
                '',
                'Optional ansible extra-vars: space-separated key=value. No leading -e.'
            )
            if (dockerSample) {
                stringParam(
                    'EXECUTION_DOCKER_TAG',
                    '',
                    'Optional: override execution.tag from cluster.yaml (empty = yaml)'
                )
            }
            stringParam(
                'GIT_SSH_CREDENTIALS_ID',
                gitCred ?: 'ssh_git',
                'Optional Jenkins SSH private-key credential id'
            )
            choiceParam('VALIDATE_STRICT', ['off', '--strict'], 'Validate: --strict or off')
            booleanParam('RUN_SMOKE', true, 'Run ./cluster smoke before deploy')
            booleanParam('SKIP_DEPLOY', false, 'Validate/smoke/plan only (no ./cluster run)')
            booleanParam('RUN_CI_PREFLIGHT', true, 'Run offline ci_preflight --skip-tests')
        }
        definition {
            cpsScm {
                scm {
                    git {
                        remote {
                            url(clusterctlUrl)
                            if (gitCred?.trim()) {
                                credentials(gitCred.trim())
                            }
                        }
                        branches('*/' + clusterctlRef)
                        extensions {
                            // Full workspace wipe before checkout (deploy JF also cleanWs in post).
                            wipeOutWorkspace()
                        }
                    }
                }
                scriptPath(jfScript)
                // Full SCM checkout for the Pipeline script — do not enable
                // lightweight checkout together with wipeOutWorkspace
                // (unreliable on some Git/Pipeline combos).
                lightweight(false)
            }
        }
    }
}
