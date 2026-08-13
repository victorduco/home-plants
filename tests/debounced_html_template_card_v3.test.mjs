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

await import("../ha/www/home-plants/debounced-html-template-card-v3-20260813.js");
const Card = customElements.get("debounced-html-template-card-v3-20260813");

function deferred() {
    let resolve;
    let reject;
    const promise = new Promise((resolvePromise, rejectPromise) => {
        resolve = resolvePromise;
        reject = rejectPromise;
    });
    return {promise, resolve, reject};
}

async function settle(turns = 8) {
    for (let index = 0; index < turns; ++index) {
        await Promise.resolve();
    }
}

function entity(entityId, state, attributes = {}) {
    return {entity_id: entityId, state, attributes};
}

function controlledApi() {
    const calls = [];
    let active = 0;
    let maxActive = 0;

    const callApi = (method, path, body) => {
        const completion = deferred();
        const call = {method, path, body, completion};
        calls.push(call);
        ++active;
        maxActive = Math.max(maxActive, active);
        completion.promise.then(
            () => { --active; },
            () => { --active; },
        );
        return completion.promise;
    };

    return {
        calls,
        callApi,
        counts: () => ({calls: calls.length, active, maxActive}),
        resolve(index, result) {
            calls[index].completion.resolve(result);
        },
        reject(index, error) {
            calls[index].completion.reject(error);
        },
    };
}

function makeHass(source, states = {}, connection = {}) {
    return {
        states,
        connection,
        callApi: source.callApi,
    };
}

function mount(config, source, states = {}, connection = {}) {
    const card = new Card();
    card.setConfig(config);
    card.isConnected = true;
    card.connectedCallback();
    card.hass = makeHass(source, states, connection);
    return card;
}

test("immutable build requires explicit entities and never subscribes to WebSocket", () => {
    assert.equal(Card.BUILD_ID, "v3-20260813.1");
    assert.equal(Card.DEBOUNCE_MS, 500);
    assert.equal(Card.MAX_WAIT_MS, 5000);

    const card = new Card();
    assert.throws(
        () => card.setConfig({content: "{{ 1 }}"}),
        /non-empty explicit 'entities'/,
    );
    assert.throws(
        () => card.setConfig({content: "{{ 1 }}", entities: [""]}),
        /non-empty entity ID string/,
    );

    const source = controlledApi();
    const connection = {
        subscribeMessage() {
            throw new Error("WebSocket subscription must never be used");
        },
    };
    mount(
        {content: "raw", do_not_parse: true},
        source,
        {},
        connection,
    );
    assert.equal(source.calls.length, 0);
});

test("relevant bursts debounce once while unrelated states are ignored", async (t) => {
    t.mock.timers.enable({apis: ["setTimeout"]});
    const source = controlledApi();
    const connection = {
        subscribeMessage() {
            throw new Error("WebSocket subscription must never be used");
        },
    };
    const watched = entity("sensor.watched", "zero");
    const card = mount(
        {
            content: "{{ states('sensor.watched') }}",
            entities: ["sensor.watched"],
            ignore_line_breaks: true,
        },
        source,
        {"sensor.watched": watched},
        connection,
    );

    t.mock.timers.tick(499);
    assert.equal(source.calls.length, 0);
    t.mock.timers.tick(1);
    assert.equal(source.calls.length, 1);
    assert.deepEqual(source.calls[0], {
        method: "POST",
        path: "template",
        body: {template: "{{ states('sensor.watched') }}"},
        completion: source.calls[0].completion,
    });
    source.resolve(0, "zero");
    await settle();

    for (let index = 0; index < 100; ++index) {
        card.hass = makeHass(
            source,
            {
                "sensor.watched": watched,
                "sensor.unrelated": entity("sensor.unrelated", String(index)),
            },
            connection,
        );
    }
    t.mock.timers.tick(5000);
    assert.equal(source.calls.length, 1, "unrelated updates must not render");

    for (let index = 0; index < 100; ++index) {
        card.hass = makeHass(
            source,
            {"sensor.watched": entity("sensor.watched", String(index))},
            connection,
        );
    }
    t.mock.timers.tick(499);
    assert.equal(source.calls.length, 1);
    t.mock.timers.tick(1);
    assert.equal(source.calls.length, 2, "one burst must make one REST call");
    source.resolve(1, "99");
    await settle();
    assert.match(card.children[0].innerHTML, /99/);
    assert.equal(source.counts().maxActive, 1);
});

test("continuous relevant changes flush at the 5000ms maximum wait", async (t) => {
    t.mock.timers.enable({apis: ["setTimeout"]});
    const source = controlledApi();
    const connection = {};
    const card = mount(
        {content: "{{ 1 }}", entities: ["sensor.watched"]},
        source,
        {"sensor.watched": entity("sensor.watched", "initial")},
        connection,
    );

    t.mock.timers.tick(500);
    source.resolve(0, "initial");
    await settle();

    card.hass = makeHass(
        source,
        {"sensor.watched": entity("sensor.watched", "0")},
        connection,
    );
    for (let index = 1; index <= 12; ++index) {
        t.mock.timers.tick(400);
        card.hass = makeHass(
            source,
            {"sensor.watched": entity("sensor.watched", String(index))},
            connection,
        );
    }
    assert.equal(source.calls.length, 1);
    t.mock.timers.tick(199);
    assert.equal(source.calls.length, 1);
    t.mock.timers.tick(1);
    assert.equal(source.calls.length, 2, "max-wait timer must bound the burst");
    source.resolve(1, "latest");
    await settle();
    assert.match(card.children[0].innerHTML, /latest/);
});

test("an in-flight render has one dirty follow-up and no overlap", async (t) => {
    t.mock.timers.enable({apis: ["setTimeout"]});
    const source = controlledApi();
    const connection = {};
    const card = mount(
        {content: "{{ 1 }}", entities: ["sensor.watched"]},
        source,
        {"sensor.watched": entity("sensor.watched", "initial")},
        connection,
    );

    t.mock.timers.tick(500);
    assert.deepEqual(source.counts(), {calls: 1, active: 1, maxActive: 1});
    for (let index = 0; index < 100; ++index) {
        card.hass = makeHass(
            source,
            {"sensor.watched": entity("sensor.watched", String(index))},
            connection,
        );
    }
    t.mock.timers.tick(5000);
    assert.equal(source.calls.length, 1, "a request must never overlap");

    source.resolve(0, "obsolete");
    await settle();
    assert.equal(source.calls.length, 2, "dirty state produces one follow-up");
    assert.doesNotMatch(card.children[0].innerHTML, /obsolete/);
    assert.deepEqual(source.counts(), {calls: 2, active: 1, maxActive: 1});

    source.resolve(1, "fresh");
    await settle();
    assert.match(card.children[0].innerHTML, /fresh/);
    assert.deepEqual(source.counts(), {calls: 2, active: 0, maxActive: 1});
});

test("a response from an older config epoch is ignored", async (t) => {
    t.mock.timers.enable({apis: ["setTimeout"]});
    const source = controlledApi();
    const card = mount(
        {content: "{{ 'old' }}", entities: ["sensor.watched"]},
        source,
        {"sensor.watched": entity("sensor.watched", "one")},
    );

    t.mock.timers.tick(500);
    assert.equal(source.calls.length, 1);
    card.setConfig({
        content: "{{ 'new' }}",
        entities: ["sensor.watched"],
        title: "New config",
    });
    source.resolve(0, "OLD RESPONSE");
    await settle();

    assert.equal(source.calls.length, 2);
    assert.equal(source.calls[1].body.template, "{{ 'new' }}");
    assert.doesNotMatch(card.children[0].innerHTML, /OLD RESPONSE/);
    source.resolve(1, "NEW RESPONSE");
    await settle();
    assert.match(card.children[0].innerHTML, /New config/);
    assert.match(card.children[0].innerHTML, /NEW RESPONSE/);
});

test("API errors are contained and a later relevant change recovers", async (t) => {
    t.mock.timers.enable({apis: ["setTimeout"]});
    const originalError = console.error;
    const errors = [];
    console.error = (...args) => errors.push(args);
    try {
        const source = controlledApi();
        const connection = {};
        const card = mount(
            {content: "{{ 1 }}", entities: ["sensor.watched"]},
            source,
            {"sensor.watched": entity("sensor.watched", "one")},
            connection,
        );

        t.mock.timers.tick(500);
        source.reject(0, new Error("template endpoint failed"));
        await settle();
        assert.equal(source.counts().active, 0);
        assert.ok(errors.some((args) => String(args[1]).includes("template endpoint failed")));

        card.hass = makeHass(
            source,
            {"sensor.watched": entity("sensor.watched", "two")},
            connection,
        );
        t.mock.timers.tick(500);
        assert.equal(source.calls.length, 2);
        source.resolve(1, "recovered");
        await settle();
        assert.match(card.children[0].innerHTML, /recovered/);
    } finally {
        console.error = originalError;
    }
});

test("rendering options and cached repaint retain legacy card behavior", async (t) => {
    t.mock.timers.enable({apis: ["setTimeout"]});
    const source = controlledApi();
    const connection = {};
    const config = {
        content: "{{ 1 }}\nsecond",
        entities: ["sensor.watched"],
        title: "First title",
    };
    const card = mount(
        config,
        source,
        {"sensor.watched": entity("sensor.watched", "one")},
        connection,
    );

    t.mock.timers.tick(500);
    assert.equal(source.calls[0].method, "POST");
    assert.equal(source.calls[0].path, "template");
    assert.equal(source.calls[0].body.template, "{{ 1 }}</br>second");
    source.resolve(0, "server result");
    await settle();
    assert.match(card.children[0].innerHTML, /First title/);
    assert.match(card.children[0].innerHTML, /server result/);

    card.setConfig({...config, title: "Reconfigured"});
    assert.equal(source.calls.length, 1, "setConfig repaint is synchronous");
    assert.match(card.children[0].innerHTML, /Reconfigured/);
    assert.match(card.children[0].innerHTML, /server result/);
    t.mock.timers.tick(500);
    source.resolve(1, "updated result");
    await settle();

    card.setConfig({...config, picture_elements_mode: true});
    assert.equal(card.children[0].name, "div");
    assert.equal(card.children[0].innerHTML, "updated result");
    assert.doesNotMatch(card.children[0].innerHTML, /First title/);

    const raw = new Card();
    raw.setConfig({content: "first\nsecond", do_not_parse: true, title: "Raw"});
    assert.equal(raw.children[0].name, "ha-card");
    assert.equal(raw.children[0].style.padding, "16px");
    assert.match(raw.children[0].innerHTML, /Raw/);
    assert.match(raw.children[0].innerHTML, /first<\/br>second/);
    raw.setConfig({
        content: "raw\ncontent",
        do_not_parse: true,
        ignore_line_breaks: true,
        picture_elements_mode: true,
        title: "Ignored",
    });
    assert.equal(raw.children[0].name, "div");
    assert.equal(raw.children[0].innerHTML, "raw\ncontent");
    assert.equal(raw.getCardSize(), 1);
});
