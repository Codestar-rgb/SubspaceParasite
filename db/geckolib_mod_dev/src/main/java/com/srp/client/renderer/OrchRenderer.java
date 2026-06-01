package com.srp.client.renderer;

import com.srp.client.model.OrchModel;
import com.srp.entity.OrchEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class OrchRenderer extends GeoEntityRenderer<OrchEntity> {

    public OrchRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new OrchModel());
    }
}
