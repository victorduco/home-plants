import assert from "node:assert/strict";
import test from "node:test";

const elements = new Map();

globalThis.HTMLElement = class {
    constructor() {
        this.children = [];
        this.isConnected = false;
    }

    appendChild(child) {
        if (!this.children.includes(child)) {
            this.children.push(child);
        }
    }

    contains(child) {
        return this.children.includes(child);
    }

    removeChild(child) {
        this.children = this.children.filter((candidate) => candidate !== child);
    }
};

globalThis.document = {
    createElement: (name) => ({name, style: {}, innerHTML: ""}),
};
globalThis.customElements = {
    define: (name, constructor) => elements.set(name, constructor),
    get: (name) => elements.get(name),
};

await import("../ha/patches/html-template-card-hotfix/html-template-card.js");
const Card = customElements.get("html-template-card");

function deferred() {
    let resolve;
    let reject;
    const promise = new Promise((resolvePromise, rejectPromise) => {
        resolve = resolvePromise;
        reject = rejectPromise;
    });
    return {promise, resolve, reject};
}

const flush = async (turns = 4) => {
    for (let index = 0; index < turns; ++index) {
        await new Promise((resolve) => setImmediate(resolve));
    }
};

async function drain(card) {
    for (let index = 0; index < 10; ++index) {
        const queue = card._lifecycleQueue;
        await queue;
        await flush(1);
        if (queue === card._lifecycleQueue && !card._reconcileScheduled) {
            return;
        }
    }
    throw new Error("card lifecycle did not settle");
}

function state(entityId, value, attributes = {}) {
    return {entity_id: entityId, state: value, attributes};
}

function createConnection({autoAck = false, autoRemove = false} = {}) {
    const attempts = [];
    let active = 0;
    let maxActive = 0;
    let removals = 0;

    const connection = {
        subscribeMessage(callback, command, options) {
            const ack = deferred();
            const remove = deferred();
            attempts.push({callback, command, options, ack, remove});
            if (autoAck) {
                ack.resolve();
            }
            return ack.promise.then(() => {
                ++active;
                maxActive = Math.max(maxActive, active);
                return async () => {
                    ++removals;
                    if (autoRemove) {
                        remove.resolve();
                    }
                    await remove.promise;
                    --active;
                };
            });
        },
    };

    return {
        connection,
        attempts,
        stats: () => ({calls: attempts.length, removals, active, maxActive}),
        ack(index) {
            attempts[index].ack.resolve();
        },
        remove(index) {
            attempts[index].remove.resolve();
        },
    };
}

function mount(config, source, states = {}) {
    const card = new Card();
    card.setConfig(config);
    card.isConnected = true;
    card.connectedCallback();
    card.hass = {connection: source.connection, states};
    return card;
}

test("HACS overlay serializes pending reconfigure through async removal", async () => {
    const source = createConnection();
    const card = mount({content: "{{ 1 }}"}, source);
    await flush();
    assert.equal(source.stats().calls, 1);

    card.setConfig({content: "{{ 2 }}"});
    await flush();
    assert.equal(source.stats().calls, 1);

    source.ack(0);
    await flush();
    assert.equal(source.stats().removals, 1);
    assert.equal(source.stats().calls, 1);

    source.remove(0);
    await flush();
    assert.equal(source.stats().calls, 2);
    source.ack(1);
    await drain(card);
    assert.equal(source.stats().maxActive, 1);
    assert.deepEqual(source.attempts[1].options, {resubscribe: false});
});

test("HACS overlay coalesces updates and retains entities/always_update", async () => {
    const source = createConnection({autoAck: true, autoRemove: true});
    const original = state("sensor.trigger", "one");
    const card = mount(
        {content: "{{ 1 }}", entities: ["sensor.trigger"]},
        source,
        {"sensor.trigger": original},
    );
    await drain(card);

    for (let index = 0; index < 1000; ++index) {
        card.hass = {
            connection: source.connection,
            states: {"sensor.trigger": original},
        };
    }
    await drain(card);
    assert.equal(source.stats().calls, 1);

    card.hass = {
        connection: source.connection,
        states: {"sensor.trigger": state("sensor.trigger", "two")},
    };
    await drain(card);
    assert.equal(source.stats().calls, 2);

    card.setConfig({content: "{{ 1 }}", always_update: true});
    await drain(card);
    const before = source.stats().calls;
    for (let index = 0; index < 100; ++index) {
        card.hass = {connection: source.connection, states: {}};
    }
    await drain(card);
    assert.equal(source.stats().calls, before + 1);
    assert.equal(source.stats().maxActive, 1);
});

test("HACS overlay disconnect/reconnect waits for old connection cleanup", async () => {
    const oldSource = createConnection();
    const newSource = createConnection({autoAck: true, autoRemove: true});
    const card = mount({content: "{{ 1 }}"}, oldSource);
    await flush();

    card.isConnected = false;
    card.disconnectedCallback();
    card.isConnected = true;
    card.connectedCallback();
    card.hass = {connection: newSource.connection, states: {}};
    await flush();
    assert.equal(newSource.stats().calls, 0);

    oldSource.ack(0);
    await flush();
    assert.equal(oldSource.stats().removals, 1);
    assert.equal(newSource.stats().calls, 0);

    oldSource.remove(0);
    await drain(card);
    assert.equal(oldSource.stats().active, 0);
    assert.equal(newSource.stats().calls, 1);
});

test("HACS overlay preserves direct rendering, title, picture, and line breaks", async () => {
    const source = createConnection({autoAck: true, autoRemove: true});
    const card = mount(
        {content: "first\nsecond", do_not_parse: true, title: "Title"},
        source,
    );
    await drain(card);
    assert.equal(source.stats().calls, 0);
    assert.equal(card.children[0].name, "ha-card");
    assert.equal(card.children[0].style.padding, "16px");
    assert.match(card.children[0].innerHTML, /Title/);
    assert.match(card.children[0].innerHTML, /first<\/br>second/);

    card.setConfig({
        content: "raw\nvalue",
        do_not_parse: true,
        ignore_line_breaks: true,
        picture_elements_mode: true,
        title: "not rendered",
    });
    assert.equal(card.children[0].name, "div");
    assert.equal(card.children[0].innerHTML, "raw\nvalue");
    assert.throws(() => card.setConfig({}), /define 'content'/);
    assert.equal(card.getCardSize(), 1);
});

test("HACS overlay catches async failures and fails closed on unsubscribe", async () => {
    const originalError = console.error;
    const errors = [];
    console.error = (...args) => errors.push(args);
    try {
        let subscribeCalls = 0;
        const connection = {
            subscribeMessage() {
                ++subscribeCalls;
                if (subscribeCalls === 1) {
                    return Promise.reject(new Error("subscribe rejected"));
                }
                return Promise.resolve(async () => {
                    throw new Error("unsubscribe rejected");
                });
            },
        };
        const first = state("sensor.demo", "one");
        const card = new Card();
        card.setConfig({content: "{{ states('sensor.demo') }}"});
        card.isConnected = true;
        card.connectedCallback();
        card.hass = {connection, states: {"sensor.demo": first}};
        await drain(card);
        assert.equal(subscribeCalls, 1);

        card.hass = {
            connection,
            states: {"sensor.demo": state("sensor.demo", "two")},
        };
        await drain(card);
        assert.equal(subscribeCalls, 2, "a later generation recovers from subscribe rejection");

        card.setConfig({content: "{{ 2 }}"});
        await drain(card);
        assert.equal(subscribeCalls, 2, "failed removal blocks an overlapping replacement");
        assert.ok(errors.some((args) => String(args[1]).includes("subscribe rejected")));
        assert.ok(errors.some((args) => String(args[1]).includes("unsubscribe rejected")));
    } finally {
        console.error = originalError;
    }
});
